"""
Celery tasks for AI document processing.

Background tasks for document analysis, summarization, and embedding generation.
"""

import logging
import time
from typing import Dict, Any, List, Optional

from celery import shared_task
from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone

from apps.documents.models import Document
from apps.ai_services.models import AIDocumentMetadata, AIProcessingQueue
from apps.ai_services.services.document_processor import get_document_processor
from apps.ai_services.services.embedding_generator import get_embedding_generator
from apps.ai_services.services.ollama_client import get_ollama_client, OllamaClientError

logger = logging.getLogger(__name__)


@shared_task(bind=True, name='ai_services.process_document', priority=3)
def process_document_task(self, document_id: str, force_reprocess: bool = False) -> Dict[str, Any]:
    """
    Process a document with complete AI analysis.
    
    Args:
        document_id: Document ID to process
        force_reprocess: Force reprocessing even if already processed
        
    Returns:
        Processing results
    """
    start_time = time.time()
    task_id = self.request.id
    
    # Create processing queue entry
    queue_entry = None
    
    try:
        # Get document
        document = Document.objects.get(id=document_id)
        
        # Create queue entry
        queue_entry = AIProcessingQueue.objects.create(
            document=document,
            task_type='all',
            priority=3,
            celery_task_id=task_id,
            input_data={'force_reprocess': force_reprocess}
        )
        queue_entry.mark_started(task_id)
        
        logger.info(f"Starting complete AI processing for document {document_id}")
        
        # Get processors
        doc_processor = get_document_processor()
        embedding_generator = get_embedding_generator()
        
        # Process document content
        ai_metadata = doc_processor.process_document(document, force_reprocess)
        
        # Generate embeddings
        embedding = embedding_generator.generate_document_embedding(document, force_reprocess)
        
        # Prepare results
        results = {
            'document_id': document_id,
            'processing_status': ai_metadata.processing_status,
            'has_summary': bool(ai_metadata.summary),
            'has_tags': bool(ai_metadata.auto_tags),
            'has_embedding': bool(embedding),
            'processing_time_ms': int((time.time() - start_time) * 1000)
        }
        
        # Mark queue entry as completed
        if queue_entry:
            queue_entry.mark_completed(
                output_data=results,
                processing_time_ms=results['processing_time_ms']
            )
        
        logger.info(f"Document {document_id} processed successfully in {results['processing_time_ms']}ms")
        return results
        
    except Document.DoesNotExist:
        error_msg = f"Document {document_id} not found"
        logger.error(error_msg)
        
        if queue_entry:
            queue_entry.mark_failed(error_msg)
            
        return {'error': error_msg, 'document_id': document_id}
        
    except Exception as e:
        error_msg = f"Document processing failed: {str(e)}"
        logger.error(f"Document {document_id} processing failed: {str(e)}")
        
        if queue_entry:
            queue_entry.mark_failed(error_msg)
            
        # Retry logic
        if self.request.retries < 3:
            logger.info(f"Retrying document processing for {document_id} (attempt {self.request.retries + 1})")
            raise self.retry(countdown=60 * (2 ** self.request.retries), max_retries=3)
        
        return {'error': error_msg, 'document_id': document_id}


@shared_task(bind=True, name='ai_services.generate_summary', priority=4)
def generate_document_summary_task(self, document_id: str) -> Dict[str, Any]:
    """
    Generate summary for a document.
    
    Args:
        document_id: Document ID to summarize
        
    Returns:
        Summary generation results
    """
    start_time = time.time()
    task_id = self.request.id
    queue_entry = None
    
    try:
        # Get document
        document = Document.objects.get(id=document_id)
        
        # Create queue entry
        queue_entry = AIProcessingQueue.objects.create(
            document=document,
            task_type='summarize',
            priority=4,
            celery_task_id=task_id
        )
        queue_entry.mark_started(task_id)
        
        logger.info(f"Generating summary for document {document_id}")
        
        # Generate summary
        doc_processor = get_document_processor()
        summary = doc_processor.generate_summary(document)
        
        # Update AI metadata
        ai_metadata, created = AIDocumentMetadata.objects.get_or_create(
            document=document,
            defaults={'organization': document.team.organization}
        )
        
        ai_metadata.summary = summary
        ai_metadata.save(update_fields=['summary', 'updated_at'])
        
        results = {
            'document_id': document_id,
            'summary': summary,
            'summary_length': len(summary.split()) if summary else 0,
            'processing_time_ms': int((time.time() - start_time) * 1000)
        }
        
        if queue_entry:
            queue_entry.mark_completed(output_data=results)
        
        logger.info(f"Summary generated for document {document_id}")
        return results
        
    except Document.DoesNotExist:
        error_msg = f"Document {document_id} not found"
        logger.error(error_msg)
        
        if queue_entry:
            queue_entry.mark_failed(error_msg)
            
        return {'error': error_msg, 'document_id': document_id}
        
    except Exception as e:
        error_msg = f"Summary generation failed: {str(e)}"
        logger.error(f"Summary generation failed for {document_id}: {str(e)}")
        
        if queue_entry:
            queue_entry.mark_failed(error_msg)
            
        return {'error': error_msg, 'document_id': document_id}


@shared_task(bind=True, name='ai_services.extract_tags', priority=4)
def extract_document_tags_task(self, document_id: str) -> Dict[str, Any]:
    """
    Extract tags from a document.
    
    Args:
        document_id: Document ID to analyze
        
    Returns:
        Tag extraction results
    """
    start_time = time.time()
    task_id = self.request.id
    queue_entry = None
    
    try:
        # Get document
        document = Document.objects.get(id=document_id)
        
        # Create queue entry
        queue_entry = AIProcessingQueue.objects.create(
            document=document,
            task_type='tag',
            priority=4,
            celery_task_id=task_id
        )
        queue_entry.mark_started(task_id)
        
        logger.info(f"Extracting tags for document {document_id}")
        
        # Extract tags
        doc_processor = get_document_processor()
        tags = doc_processor.extract_tags(document)
        
        # Update AI metadata
        ai_metadata, created = AIDocumentMetadata.objects.get_or_create(
            document=document,
            defaults={'organization': document.team.organization}
        )
        
        ai_metadata.auto_tags = tags
        ai_metadata.save(update_fields=['auto_tags', 'updated_at'])
        
        results = {
            'document_id': document_id,
            'tags': tags,
            'tag_count': len(tags),
            'processing_time_ms': int((time.time() - start_time) * 1000)
        }
        
        if queue_entry:
            queue_entry.mark_completed(output_data=results)
        
        logger.info(f"Tags extracted for document {document_id}: {tags}")
        return results
        
    except Document.DoesNotExist:
        error_msg = f"Document {document_id} not found"
        logger.error(error_msg)
        
        if queue_entry:
            queue_entry.mark_failed(error_msg)
            
        return {'error': error_msg, 'document_id': document_id}
        
    except Exception as e:
        error_msg = f"Tag extraction failed: {str(e)}"
        logger.error(f"Tag extraction failed for {document_id}: {str(e)}")
        
        if queue_entry:
            queue_entry.mark_failed(error_msg)
            
        return {'error': error_msg, 'document_id': document_id}


@shared_task(bind=True, name='ai_services.generate_embedding', priority=2)
def generate_document_embedding_task(self, document_id: str, force_regenerate: bool = False) -> Dict[str, Any]:
    """
    Generate embedding for a document.
    
    Args:
        document_id: Document ID to process
        force_regenerate: Force regeneration of existing embedding
        
    Returns:
        Embedding generation results
    """
    start_time = time.time()
    task_id = self.request.id
    queue_entry = None
    
    try:
        # Get document
        document = Document.objects.get(id=document_id)
        
        # Create queue entry
        queue_entry = AIProcessingQueue.objects.create(
            document=document,
            task_type='embed',
            priority=2,
            celery_task_id=task_id,
            input_data={'force_regenerate': force_regenerate}
        )
        queue_entry.mark_started(task_id)
        
        logger.info(f"Generating embedding for document {document_id}")
        
        # Generate embedding
        embedding_generator = get_embedding_generator()
        embedding = embedding_generator.generate_document_embedding(document, force_regenerate)
        
        results = {
            'document_id': document_id,
            'has_embedding': bool(embedding),
            'embedding_dimensions': len(embedding) if embedding else 0,
            'processing_time_ms': int((time.time() - start_time) * 1000)
        }
        
        if queue_entry:
            queue_entry.mark_completed(output_data=results)
        
        logger.info(f"Embedding generated for document {document_id}")
        return results
        
    except Document.DoesNotExist:
        error_msg = f"Document {document_id} not found"
        logger.error(error_msg)
        
        if queue_entry:
            queue_entry.mark_failed(error_msg)
            
        return {'error': error_msg, 'document_id': document_id}
        
    except Exception as e:
        error_msg = f"Embedding generation failed: {str(e)}"
        logger.error(f"Embedding generation failed for {document_id}: {str(e)}")
        
        if queue_entry:
            queue_entry.mark_failed(error_msg)
            
        return {'error': error_msg, 'document_id': document_id}


@shared_task(bind=True, name='ai_services.batch_process_documents', priority=5)
def batch_process_documents_task(self, document_ids: List[str], force_reprocess: bool = False) -> Dict[str, Any]:
    """
    Process multiple documents in batch.
    
    Args:
        document_ids: List of document IDs to process
        force_reprocess: Force reprocessing of existing data
        
    Returns:
        Batch processing results
    """
    start_time = time.time()
    
    logger.info(f"Starting batch processing of {len(document_ids)} documents")
    
    results = {
        'total_documents': len(document_ids),
        'processed': 0,
        'failed': 0,
        'errors': [],
        'processing_time_ms': 0
    }
    
    # Process each document
    for doc_id in document_ids:
        try:
            # Queue individual processing task
            process_document_task.delay(doc_id, force_reprocess)
            results['processed'] += 1
            
        except Exception as e:
            error_msg = f"Failed to queue processing for document {doc_id}: {str(e)}"
            results['errors'].append(error_msg)
            results['failed'] += 1
            logger.error(error_msg)
    
    results['processing_time_ms'] = int((time.time() - start_time) * 1000)
    
    logger.info(f"Batch processing queued: {results['processed']} successful, {results['failed']} failed")
    return results


@shared_task(bind=True, name='ai_services.cleanup_expired_cache')
def cleanup_expired_cache_task(self) -> Dict[str, Any]:
    """
    Clean up expired AI suggestions cache entries.
    
    Returns:
        Cleanup results
    """
    start_time = time.time()
    
    try:
        from apps.ai_services.models import AISuggestionsCache
        
        # Remove expired entries
        expired_count = AISuggestionsCache.cleanup_expired()
        
        results = {
            'expired_entries_removed': expired_count,
            'processing_time_ms': int((time.time() - start_time) * 1000)
        }
        
        logger.info(f"Cleaned up {expired_count} expired cache entries")
        return results
        
    except Exception as e:
        error_msg = f"Cache cleanup failed: {str(e)}"
        logger.error(error_msg)
        return {'error': error_msg}


@shared_task(bind=True, name='ai_services.health_check_ollama')
def health_check_ollama_task(self) -> Dict[str, Any]:
    """
    Perform health check on Ollama server.
    
    Returns:
        Health check results
    """
    start_time = time.time()
    
    try:
        ollama_client = get_ollama_client()
        
        # Check server health
        is_healthy = ollama_client.health_check()
        
        # Get available models if healthy
        models = []
        if is_healthy:
            models = ollama_client.list_models()
        
        results = {
            'is_healthy': is_healthy,
            'available_models': len(models),
            'models': [model.get('name', 'unknown') for model in models],
            'default_model': ollama_client.default_model,
            'embedding_model': ollama_client.embedding_model,
            'server_url': ollama_client.base_url,
            'check_time_ms': int((time.time() - start_time) * 1000)
        }
        
        if is_healthy:
            logger.info(f"Ollama health check passed - {len(models)} models available")
        else:
            logger.warning("Ollama health check failed")
            
        return results
        
    except Exception as e:
        error_msg = f"Ollama health check failed: {str(e)}"
        logger.error(error_msg)
        return {
            'is_healthy': False,
            'error': error_msg,
            'check_time_ms': int((time.time() - start_time) * 1000)
        }


@shared_task(bind=True, name='ai_services.retry_failed_processing')
def retry_failed_processing_task(self, max_retries: int = 3) -> Dict[str, Any]:
    """
    Retry failed AI processing tasks.
    
    Args:
        max_retries: Maximum number of retries to attempt
        
    Returns:
        Retry results
    """
    start_time = time.time()
    
    try:
        # Find failed processing entries that should be retried
        failed_metadata = AIDocumentMetadata.objects.filter(
            processing_status='failed',
            retry_count__lt=max_retries
        ).select_related('document')
        
        results = {
            'found_failed': failed_metadata.count(),
            'retried': 0,
            'skipped': 0,
            'errors': []
        }
        
        for metadata in failed_metadata:
            try:
                # Queue for reprocessing
                process_document_task.delay(str(metadata.document.id), force_reprocess=True)
                results['retried'] += 1
                
            except Exception as e:
                error_msg = f"Failed to retry processing for document {metadata.document.id}: {str(e)}"
                results['errors'].append(error_msg)
                results['skipped'] += 1
                logger.error(error_msg)
        
        results['processing_time_ms'] = int((time.time() - start_time) * 1000)
        
        logger.info(f"Retry processing: {results['retried']} queued, {results['skipped']} skipped")
        return results
        
    except Exception as e:
        error_msg = f"Retry failed processing task failed: {str(e)}"
        logger.error(error_msg)
        return {'error': error_msg}
