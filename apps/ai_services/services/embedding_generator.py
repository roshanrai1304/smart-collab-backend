"""
Embedding generator service for Smart Collaborative Backend.

Handles vector embedding generation and semantic search functionality.
"""

import hashlib
import logging
import time
from typing import List, Dict, Any, Optional, Tuple
from django.core.cache import cache
from django.db import connection
from pgvector.django import CosineDistance

from apps.documents.models import Document
from apps.ai_services.models import AIDocumentMetadata
from apps.ai_services.services.ollama_client import get_ollama_client, OllamaClientError

logger = logging.getLogger(__name__)


class EmbeddingGenerator:
    """
    Service for generating and managing document embeddings.
    
    Handles:
    - Embedding generation using Ollama
    - Vector storage in PostgreSQL with pgvector
    - Semantic search functionality
    - Embedding cache management
    """
    
    def __init__(self):
        self.ollama_client = get_ollama_client()
        self.cache_timeout = 60 * 60 * 24 * 7  # 7 days for embeddings
        self.embedding_model = self.ollama_client.embedding_model
    
    def generate_document_embedding(self, document: Document, force_regenerate: bool = False) -> Optional[List[float]]:
        """
        Generate embedding for a document.
        
        Args:
            document: Document to generate embedding for
            force_regenerate: Force regeneration even if embedding exists
            
        Returns:
            Embedding vector or None if generation fails
        """
        try:
            # Get or create AI metadata
            ai_metadata, created = AIDocumentMetadata.objects.get_or_create(
                document=document,
                defaults={
                    'organization': document.team.organization,
                    'processing_status': 'pending'
                }
            )
            
            # Check if embedding already exists and is valid
            if not force_regenerate and ai_metadata.embedding_vector:
                logger.info(f"Using existing embedding for document {document.id}")
                return list(ai_metadata.embedding_vector)
            
            # Extract document text
            content_text = self._extract_document_text(document)
            
            if not content_text or len(content_text.strip()) < 10:
                logger.warning(f"Document {document.id} has insufficient content for embedding")
                return None
            
            # Generate embedding
            start_time = time.time()
            embedding = self._generate_text_embedding(content_text)
            
            if embedding:
                # Store embedding in database
                ai_metadata.embedding_vector = embedding
                ai_metadata.embedding_model = self.embedding_model
                ai_metadata.save(update_fields=['embedding_vector', 'embedding_model', 'updated_at'])
                
                # Log performance
                duration = time.time() - start_time
                logger.info(f"Generated embedding for document {document.id} in {duration:.2f}s")
                
                return embedding
            
            return None
            
        except Exception as e:
            logger.error(f"Embedding generation failed for document {document.id}: {str(e)}")
            return None
    
    def _extract_document_text(self, document: Document) -> str:
        """Extract plain text from document."""
        if document.content_text:
            return document.content_text
        
        if isinstance(document.content, dict):
            return document._extract_text_from_rich_content(document.content)
        elif isinstance(document.content, str):
            return document.content
        
        return ""
    
    def _generate_text_embedding(self, text: str) -> Optional[List[float]]:
        """
        Generate embedding for text content.
        
        Args:
            text: Text to generate embedding for
            
        Returns:
            Embedding vector or None if generation fails
        """
        # Create cache key
        text_hash = hashlib.sha256(text.encode()).hexdigest()
        cache_key = f"embedding:{self.embedding_model}:{text_hash}"
        
        # Check cache first
        cached_embedding = cache.get(cache_key)
        if cached_embedding:
            logger.info("Using cached embedding")
            return cached_embedding
        
        try:
            # Truncate text if too long (embedding models have token limits)
            max_chars = 8000  # Approximate limit for most embedding models
            if len(text) > max_chars:
                text = text[:max_chars] + "..."
                logger.info(f"Truncated text to {max_chars} characters for embedding")
            
            # Generate embedding using qwen3-embedding:8b with 4096 dimensions
            from django.conf import settings
            dimensions = getattr(settings, 'EMBEDDING_DIMENSIONS', 4096)
            embedding = self.ollama_client.generate_embeddings(text, self.embedding_model, dimensions=dimensions)
            
            if embedding:
                # Cache the embedding
                cache.set(cache_key, embedding, self.cache_timeout)
                return embedding
            
            return None
            
        except OllamaClientError as e:
            logger.error(f"Ollama embedding generation failed: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error generating embedding: {str(e)}")
            return None
    
    def semantic_search(
        self, 
        query: str, 
        team_id: str = None,
        organization_id: str = None,
        limit: int = 10,
        similarity_threshold: float = 0.7
    ) -> List[Dict[str, Any]]:
        """
        Perform semantic search using vector similarity.
        
        Args:
            query: Search query text
            team_id: Limit search to specific team
            organization_id: Limit search to specific organization
            limit: Maximum number of results
            similarity_threshold: Minimum similarity score (0-1)
            
        Returns:
            List of search results with similarity scores
        """
        try:
            # Generate query embedding
            query_embedding = self._generate_text_embedding(query)
            
            if not query_embedding:
                logger.warning("Failed to generate query embedding")
                return []
            
            # Build query
            queryset = AIDocumentMetadata.objects.filter(
                embedding_vector__isnull=False,
                processing_status='completed'
            ).select_related('document', 'document__team', 'organization')
            
            # Apply filters
            if team_id:
                queryset = queryset.filter(document__team_id=team_id)
            elif organization_id:
                queryset = queryset.filter(organization_id=organization_id)
            
            # Calculate cosine similarity and filter by threshold
            results = []
            
            # Use raw SQL for better performance with pgvector
            with connection.cursor() as cursor:
                # Build WHERE clause
                where_conditions = ["ai.embedding_vector IS NOT NULL", "ai.processing_status = 'completed'"]
                params = [query_embedding]
                
                if team_id:
                    where_conditions.append("d.team_id = %s")
                    params.append(team_id)
                elif organization_id:
                    where_conditions.append("ai.organization_id = %s")
                    params.append(organization_id)
                
                where_clause = " AND ".join(where_conditions)
                
                sql = f"""
                SELECT 
                    d.id,
                    d.title,
                    d.content_text,
                    d.created_at,
                    d.updated_at,
                    ai.summary,
                    ai.auto_tags,
                    ai.detected_content_type,
                    1 - (ai.embedding_vector <=> %s) AS similarity
                FROM ai_document_metadata ai
                JOIN documents d ON ai.document_id = d.id
                WHERE {where_clause}
                    AND (1 - (ai.embedding_vector <=> %s)) >= %s
                ORDER BY similarity DESC
                LIMIT %s
                """
                
                params.extend([query_embedding, similarity_threshold, limit])
                
                cursor.execute(sql, params)
                rows = cursor.fetchall()
                
                # Convert to result format
                for row in rows:
                    results.append({
                        'document_id': str(row[0]),
                        'title': row[1],
                        'content_preview': row[2][:200] + '...' if row[2] and len(row[2]) > 200 else row[2],
                        'created_at': row[3],
                        'updated_at': row[4],
                        'summary': row[5],
                        'tags': row[6] if row[6] else [],
                        'content_type': row[7],
                        'similarity_score': float(row[8])
                    })
            
            logger.info(f"Semantic search returned {len(results)} results for query: {query[:50]}...")
            return results
            
        except Exception as e:
            logger.error(f"Semantic search failed: {str(e)}")
            return []
    
    def find_similar_documents(
        self, 
        document_id: str, 
        limit: int = 5,
        similarity_threshold: float = 0.6
    ) -> List[Dict[str, Any]]:
        """
        Find documents similar to a given document.
        
        Args:
            document_id: ID of the reference document
            limit: Maximum number of similar documents to return
            similarity_threshold: Minimum similarity score
            
        Returns:
            List of similar documents with similarity scores
        """
        try:
            # Get the reference document's embedding
            reference_metadata = AIDocumentMetadata.objects.select_related('document').get(
                document_id=document_id,
                embedding_vector__isnull=False
            )
            
            reference_embedding = list(reference_metadata.embedding_vector)
            
            # Find similar documents in the same organization
            with connection.cursor() as cursor:
                sql = """
                SELECT 
                    d.id,
                    d.title,
                    d.content_text,
                    ai.summary,
                    ai.auto_tags,
                    ai.detected_content_type,
                    1 - (ai.embedding_vector <=> %s) AS similarity
                FROM ai_document_metadata ai
                JOIN documents d ON ai.document_id = d.id
                WHERE ai.organization_id = %s
                    AND ai.document_id != %s
                    AND ai.embedding_vector IS NOT NULL
                    AND ai.processing_status = 'completed'
                    AND (1 - (ai.embedding_vector <=> %s)) >= %s
                ORDER BY similarity DESC
                LIMIT %s
                """
                
                cursor.execute(sql, [
                    reference_embedding,
                    str(reference_metadata.organization_id),
                    document_id,
                    reference_embedding,
                    similarity_threshold,
                    limit
                ])
                
                rows = cursor.fetchall()
                
                results = []
                for row in rows:
                    results.append({
                        'document_id': str(row[0]),
                        'title': row[1],
                        'content_preview': row[2][:200] + '...' if row[2] and len(row[2]) > 200 else row[2],
                        'summary': row[3],
                        'tags': row[4] if row[4] else [],
                        'content_type': row[5],
                        'similarity_score': float(row[6])
                    })
                
                return results
            
        except AIDocumentMetadata.DoesNotExist:
            logger.warning(f"No embedding found for document {document_id}")
            return []
        except Exception as e:
            logger.error(f"Similar document search failed: {str(e)}")
            return []
    
    def batch_generate_embeddings(
        self, 
        document_ids: List[str], 
        force_regenerate: bool = False
    ) -> Dict[str, Any]:
        """
        Generate embeddings for multiple documents in batch.
        
        Args:
            document_ids: List of document IDs
            force_regenerate: Force regeneration of existing embeddings
            
        Returns:
            Processing results summary
        """
        results = {
            'processed': 0,
            'skipped': 0,
            'failed': 0,
            'errors': []
        }
        
        for doc_id in document_ids:
            try:
                document = Document.objects.get(id=doc_id)
                embedding = self.generate_document_embedding(document, force_regenerate)
                
                if embedding:
                    results['processed'] += 1
                else:
                    results['skipped'] += 1
                    
            except Document.DoesNotExist:
                error_msg = f"Document {doc_id} not found"
                results['errors'].append(error_msg)
                results['failed'] += 1
                logger.warning(error_msg)
                
            except Exception as e:
                error_msg = f"Embedding generation failed for document {doc_id}: {str(e)}"
                results['errors'].append(error_msg)
                results['failed'] += 1
                logger.error(error_msg)
        
        return results
    
    def update_embedding_if_needed(self, document: Document) -> bool:
        """
        Update document embedding if the document has been modified.
        
        Args:
            document: Document to check and update
            
        Returns:
            True if embedding was updated, False otherwise
        """
        try:
            ai_metadata = AIDocumentMetadata.objects.get(document=document)
            
            # Check if update is needed
            if (not ai_metadata.embedding_vector or 
                not ai_metadata.last_processed or
                document.updated_at > ai_metadata.last_processed):
                
                embedding = self.generate_document_embedding(document, force_regenerate=True)
                return embedding is not None
            
            return False
            
        except AIDocumentMetadata.DoesNotExist:
            # Generate embedding for new document
            embedding = self.generate_document_embedding(document)
            return embedding is not None
        except Exception as e:
            logger.error(f"Error updating embedding for document {document.id}: {str(e)}")
            return False
    
    def get_embedding_stats(self, organization_id: str = None) -> Dict[str, Any]:
        """
        Get statistics about embeddings in the system.
        
        Args:
            organization_id: Limit stats to specific organization
            
        Returns:
            Statistics dictionary
        """
        try:
            queryset = AIDocumentMetadata.objects.all()
            
            if organization_id:
                queryset = queryset.filter(organization_id=organization_id)
            
            total_documents = queryset.count()
            with_embeddings = queryset.filter(embedding_vector__isnull=False).count()
            processing = queryset.filter(processing_status='processing').count()
            failed = queryset.filter(processing_status='failed').count()
            
            return {
                'total_documents': total_documents,
                'with_embeddings': with_embeddings,
                'processing': processing,
                'failed': failed,
                'completion_rate': (with_embeddings / total_documents * 100) if total_documents > 0 else 0,
                'embedding_model': self.embedding_model
            }
            
        except Exception as e:
            logger.error(f"Error getting embedding stats: {str(e)}")
            return {}


# Global generator instance
_embedding_generator = None


def get_embedding_generator() -> EmbeddingGenerator:
    """
    Get singleton EmbeddingGenerator instance.
    
    Returns:
        EmbeddingGenerator instance
    """
    global _embedding_generator
    if _embedding_generator is None:
        _embedding_generator = EmbeddingGenerator()
    return _embedding_generator
