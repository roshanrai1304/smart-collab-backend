"""
Document processor service for Smart Collaborative Backend.

Handles document analysis, summarization, and content extraction.
"""

import hashlib
import logging
import time
from typing import Dict, List, Optional, Any, Tuple
from django.core.cache import cache
from django.utils import timezone

from apps.documents.models import Document
from apps.ai_services.models import AIDocumentMetadata
from apps.ai_services.services.ollama_client import get_ollama_client, OllamaClientError

logger = logging.getLogger(__name__)


class DocumentProcessor:
    """
    Service for processing documents with AI.
    
    Handles:
    - Document summarization
    - Key point extraction
    - Content analysis
    - Metadata generation
    """
    
    def __init__(self):
        self.ollama_client = get_ollama_client()
        self.cache_timeout = 60 * 60 * 24  # 24 hours
    
    def process_document(self, document: Document, force_reprocess: bool = False, use_streaming: bool = False) -> AIDocumentMetadata:
        """
        Process a document with AI analysis using advanced optimization features.
        
        Args:
            document: Document to process
            force_reprocess: Force reprocessing even if already processed
            use_streaming: Use streaming processing for real-time updates
            
        Returns:
            AIDocumentMetadata instance with results
        """
        start_time = time.time()
        
        try:
            # Get or create AI metadata
            ai_metadata, created = AIDocumentMetadata.objects.get_or_create(
                document=document,
                defaults={
                    'organization': document.team.organization,
                    'processing_status': 'pending'
                }
            )
            
            # Check if processing is needed
            if not created and not force_reprocess and not ai_metadata.is_processing_needed():
                logger.info(f"Document {document.id} already processed, skipping")
                return ai_metadata
            
            # Mark as processing
            ai_metadata.mark_processing_started()
            
            # Extract text content
            content_text = self._extract_document_text(document)
            
            if not content_text or len(content_text.strip()) < 10:
                ai_metadata.processing_status = 'skipped'
                ai_metadata.error_message = 'Document content too short for processing'
                ai_metadata.save()
                return ai_metadata
            
            # Get team context for optimization
            from apps.ai_services.services.context_processor import get_contextual_processor
            context_processor = get_contextual_processor()
            
            # Optimize processing parameters based on team context
            base_params = {
                'max_summary_length': 200,
                'max_tags': 10,
                'use_chunking': len(content_text) > 2000,
                'parallel_processing': True
            }
            
            optimized_params = context_processor.optimize_processing_for_context(
                content_text,
                str(document.team.id),
                str(document.created_by.id) if document.created_by else None,
                base_params
            )
            
            # Use streaming processing if requested
            if use_streaming:
                results = self._stream_analyze_document_content(content_text, document, optimized_params)
            else:
                # Use chunking for large documents
                if optimized_params.get('use_chunking', False):
                    results = self._analyze_document_content_chunked(content_text, optimized_params)
                else:
                    results = self._analyze_document_content(content_text, optimized_params)
            
            # Update metadata with results
            ai_metadata.summary = results.get('summary', '')
            ai_metadata.key_points = results.get('key_points', [])
            ai_metadata.auto_tags = results.get('tags', [])
            ai_metadata.sentiment_score = results.get('sentiment_score')
            ai_metadata.detected_content_type = results.get('content_type', 'other')
            ai_metadata.readability_score = results.get('readability_score')
            ai_metadata.confidence_scores = results.get('confidence_scores', {})
            ai_metadata.model_version = self.ollama_client.default_model
            
            # Calculate processing time
            processing_time = int((time.time() - start_time) * 1000)
            ai_metadata.mark_processing_completed(processing_time)
            
            logger.info(f"Document {document.id} processed successfully in {processing_time}ms")
            
            return ai_metadata
            
        except Exception as e:
            logger.error(f"Document processing failed for {document.id}: {str(e)}")
            
            if 'ai_metadata' in locals():
                ai_metadata.mark_processing_failed(str(e))
            
            raise
    
    def _extract_document_text(self, document: Document) -> str:
        """
        Extract plain text from document content.
        
        Args:
            document: Document instance
            
        Returns:
            Plain text content
        """
        # Use existing content_text if available
        if document.content_text:
            return document.content_text
        
        # Extract from rich content if needed
        if isinstance(document.content, dict):
            return document._extract_text_from_rich_content(document.content)
        elif isinstance(document.content, str):
            return document.content
        
        return ""
    
    def _analyze_document_content(self, content: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Perform comprehensive AI analysis of document content.
        
        Args:
            content: Document text content
            params: Processing parameters for optimization
            
        Returns:
            Dictionary with analysis results
        """
        params = params or {}
        results = {}
        
        # Create content hash for caching
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        cache_key = f"doc_analysis:{content_hash}"
        
        # Check cache first
        cached_results = cache.get(cache_key)
        if cached_results:
            logger.info("Using cached document analysis results")
            return cached_results
        
        try:
            # Generate summary
            logger.info("Generating document summary...")
            summary = self.ollama_client.summarize_document(content, max_length=200)
            results['summary'] = summary
            
            # Extract tags
            logger.info("Extracting document tags...")
            tags = self.ollama_client.extract_tags(content, max_tags=10)
            results['tags'] = tags
            
            # Analyze sentiment
            logger.info("Analyzing document sentiment...")
            sentiment_score = self.ollama_client.analyze_sentiment(content)
            results['sentiment_score'] = sentiment_score
            
            # Detect content type
            logger.info("Detecting content type...")
            content_type = self.ollama_client.detect_content_type(content)
            results['content_type'] = content_type
            
            # Extract key points
            logger.info("Extracting key points...")
            key_points = self._extract_key_points(content)
            results['key_points'] = key_points
            
            # Calculate readability score
            readability_score = self._calculate_readability_score(content)
            results['readability_score'] = readability_score
            
            # Set confidence scores (placeholder for now)
            results['confidence_scores'] = {
                'summary': 0.85,
                'tags': 0.80,
                'sentiment': 0.75,
                'content_type': 0.90,
                'key_points': 0.80
            }
            
            # Cache results
            cache.set(cache_key, results, self.cache_timeout)
            
            return results
            
        except OllamaClientError as e:
            logger.error(f"Ollama client error during analysis: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error during document analysis: {str(e)}")
            raise
    
    def _extract_key_points(self, content: str, max_points: int = 5) -> List[Dict[str, Any]]:
        """
        Extract key points from document content.
        
        Args:
            content: Document text
            max_points: Maximum number of key points
            
        Returns:
            List of key points with metadata
        """
        try:
            system_prompt = f"""You are an expert at analyzing documents and extracting key points. Extract up to {max_points} key points from the content. For each key point, provide a brief, clear statement. Return the result as a JSON array of objects with 'point' and 'importance' (1-10) fields."""
            
            prompt = f"""Extract the key points from this document:

{content}

Key points (JSON format):"""

            response = self.ollama_client.generate_text(
                prompt=prompt,
                system_prompt=system_prompt,
                max_tokens=500,
                temperature=0.3
            )
            
            # Try to parse JSON response
            import json
            try:
                key_points = json.loads(response)
                if isinstance(key_points, list):
                    return key_points[:max_points]
            except json.JSONDecodeError:
                pass
            
            # Fallback: parse as simple list
            lines = response.strip().split('\n')
            key_points = []
            for i, line in enumerate(lines[:max_points]):
                line = line.strip()
                if line and not line.startswith(('```', '[')):
                    # Remove bullet points and numbering
                    line = line.lstrip('•-*1234567890. ')
                    if line:
                        key_points.append({
                            'point': line,
                            'importance': max(1, 10 - i)  # Decreasing importance
                        })
            
            return key_points
            
        except Exception as e:
            logger.warning(f"Key point extraction failed: {str(e)}")
            return []
    
    def _calculate_readability_score(self, content: str) -> Optional[int]:
        """
        Calculate Flesch Reading Ease score.
        
        Args:
            content: Document text
            
        Returns:
            Readability score (0-100, higher is easier)
        """
        try:
            import re
            
            # Count sentences
            sentences = len(re.findall(r'[.!?]+', content))
            if sentences == 0:
                return None
            
            # Count words
            words = len(content.split())
            if words == 0:
                return None
            
            # Count syllables (approximate)
            syllables = 0
            for word in content.lower().split():
                word = re.sub(r'[^a-z]', '', word)
                if word:
                    # Simple syllable counting
                    vowels = len(re.findall(r'[aeiouy]', word))
                    if word.endswith('e'):
                        vowels -= 1
                    if vowels == 0:
                        vowels = 1
                    syllables += vowels
            
            # Flesch Reading Ease formula
            if sentences > 0 and words > 0:
                score = 206.835 - (1.015 * (words / sentences)) - (84.6 * (syllables / words))
                return max(0, min(100, int(score)))
            
            return None
            
        except Exception as e:
            logger.warning(f"Readability calculation failed: {str(e)}")
            return None
    
    def generate_summary(self, document: Document, max_length: int = 200) -> str:
        """
        Generate a summary for a document.
        
        Args:
            document: Document to summarize
            max_length: Maximum summary length in words
            
        Returns:
            Generated summary
        """
        try:
            content = self._extract_document_text(document)
            
            if not content:
                return "No content available for summarization."
            
            return self.ollama_client.summarize_document(content, max_length)
            
        except Exception as e:
            logger.error(f"Summary generation failed for document {document.id}: {str(e)}")
            return "Summary generation failed."
    
    def extract_tags(self, document: Document, max_tags: int = 10) -> List[str]:
        """
        Extract tags from a document.
        
        Args:
            document: Document to analyze
            max_tags: Maximum number of tags
            
        Returns:
            List of extracted tags
        """
        try:
            content = self._extract_document_text(document)
            
            if not content:
                return []
            
            return self.ollama_client.extract_tags(content, max_tags)
            
        except Exception as e:
            logger.error(f"Tag extraction failed for document {document.id}: {str(e)}")
            return []
    
    def batch_process_documents(self, document_ids: List[str], force_reprocess: bool = False) -> Dict[str, Any]:
        """
        Process multiple documents in batch.
        
        Args:
            document_ids: List of document IDs to process
            force_reprocess: Force reprocessing
            
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
                self.process_document(document, force_reprocess)
                results['processed'] += 1
                
            except Document.DoesNotExist:
                error_msg = f"Document {doc_id} not found"
                results['errors'].append(error_msg)
                results['failed'] += 1
                logger.warning(error_msg)
                
            except Exception as e:
                error_msg = f"Processing failed for document {doc_id}: {str(e)}"
                results['errors'].append(error_msg)
                results['failed'] += 1
                logger.error(error_msg)
        
        return results


# Global processor instance
_document_processor = None


def get_document_processor() -> DocumentProcessor:
    """
    Get singleton DocumentProcessor instance.
    
    Returns:
        DocumentProcessor instance
    """
    global _document_processor
    if _document_processor is None:
        _document_processor = DocumentProcessor()
    return _document_processor


# Additional methods for DocumentProcessor class
def _analyze_document_content_chunked(self, content: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Analyze document content using chunking for parallel processing.
    
    Args:
        content: Document text content
        params: Processing parameters
        
    Returns:
        Dictionary with analysis results
    """
    from apps.ai_services.services.document_chunker import get_document_chunker
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    params = params or {}
    chunker = get_document_chunker()
    
    # Chunk the document
    chunks = chunker.chunk_document(content, strategy="auto")
    
    if len(chunks) <= 1:
        # No benefit from chunking, use regular processing
        return self._analyze_document_content(content, params)
    
    logger.info(f"Processing document with {len(chunks)} chunks")
    
    # Process chunks in parallel
    chunk_results = []
    max_workers = min(3, len(chunks))  # Limit concurrent processing
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit chunk processing tasks
        future_to_chunk = {}
        for i, chunk in enumerate(chunks):
            future = executor.submit(self._process_single_chunk, chunk, params, i)
            future_to_chunk[future] = chunk
        
        # Collect results
        for future in as_completed(future_to_chunk):
            chunk = future_to_chunk[future]
            try:
                chunk_result = future.result()
                chunk_results.append(chunk_result)
            except Exception as e:
                logger.error(f"Chunk processing failed: {str(e)}")
                # Continue with other chunks
    
    # Combine chunk results
    return self._combine_chunk_results(chunk_results, content, params)


def _process_single_chunk(self, chunk, params: Dict[str, Any], chunk_index: int) -> Dict[str, Any]:
    """Process a single document chunk."""
    try:
        # Use optimal model for the task
        content_length = len(chunk.content)
        
        # Fast processing for chunks
        summary = self.ollama_client.summarize_document(
            chunk.content,
            max_length=params.get('chunk_summary_length', 100),
            model=self.ollama_client.get_optimal_model('summarization', content_length)
        )
        
        tags = self.ollama_client.extract_tags(
            chunk.content,
            max_tags=params.get('chunk_max_tags', 5),
            model=self.ollama_client.get_optimal_model('tagging', content_length)
        )
        
        return {
            'chunk_index': chunk_index,
            'summary': summary,
            'tags': tags,
            'word_count': chunk.word_count,
            'chunk_type': chunk.chunk_type
        }
    except Exception as e:
        logger.error(f"Single chunk processing failed: {str(e)}")
        return {
            'chunk_index': chunk_index,
            'summary': '',
            'tags': [],
            'error': str(e)
        }


def _combine_chunk_results(self, chunk_results: List[Dict[str, Any]], full_content: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Combine results from multiple chunks into final analysis."""
    if not chunk_results:
        return {'summary': '', 'tags': [], 'key_points': []}
    
    # Combine summaries
    chunk_summaries = [result['summary'] for result in chunk_results if result.get('summary')]
    combined_summary_text = ' '.join(chunk_summaries)
    
    # Generate final summary from chunk summaries
    final_summary = self.ollama_client.summarize_document(
        combined_summary_text,
        max_length=params.get('max_summary_length', 200),
        model=self.ollama_client.get_optimal_model('summarization')
    )
    
    # Combine and deduplicate tags
    all_tags = []
    for result in chunk_results:
        all_tags.extend(result.get('tags', []))
    
    # Remove duplicates and get most frequent tags
    from collections import Counter
    tag_counts = Counter(all_tags)
    final_tags = [tag for tag, count in tag_counts.most_common(params.get('max_tags', 10))]
    
    # Generate other analyses on the full content (but with optimized models)
    content_type = self.ollama_client.detect_content_type(
        full_content[:1000],  # Use first 1000 chars for speed
        model=self.ollama_client.get_optimal_model('classification')
    )
    
    sentiment_score = self.ollama_client.analyze_sentiment(
        full_content[:2000],  # Use first 2000 chars for speed
        model=self.ollama_client.get_optimal_model('sentiment')
    )
    
    # Extract key points from the combined summaries
    key_points = self.ollama_client.extract_key_points(combined_summary_text)
    
    return {
        'summary': final_summary,
        'tags': final_tags,
        'key_points': key_points,
        'content_type': content_type,
        'sentiment_score': sentiment_score,
        'processing_method': 'chunked',
        'chunks_processed': len(chunk_results)
    }


# Monkey patch the methods to the DocumentProcessor class
DocumentProcessor._analyze_document_content_chunked = _analyze_document_content_chunked
DocumentProcessor._process_single_chunk = _process_single_chunk
DocumentProcessor._combine_chunk_results = _combine_chunk_results
