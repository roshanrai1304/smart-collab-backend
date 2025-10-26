"""
Django signals for AI services.

Automatically triggers AI processing when documents are created or updated.
"""

import logging
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.conf import settings

from apps.documents.models import Document
from apps.ai_services.models import AIDocumentMetadata

# Import tasks (will be available after Celery is configured)
try:
    from apps.ai_services.tasks.document_tasks import (
        process_document_task,
        generate_document_summary_task,
        extract_document_tags_task,
        generate_document_embedding_task
    )
    TASKS_AVAILABLE = True
except ImportError:
    TASKS_AVAILABLE = False

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Document)
def process_document_on_save(sender, instance, created, **kwargs):
    """
    Automatically process document with AI when created or significantly updated.
    
    Args:
        sender: Document model class
        instance: Document instance
        created: Whether this is a new document
        **kwargs: Additional signal kwargs
    """
    # Skip if AI processing is disabled
    if not getattr(settings, 'AI_PROCESSING_ENABLED', True):
        return
    
    # Skip if tasks are not available (e.g., during migrations)
    if not TASKS_AVAILABLE:
        return
    
    try:
        # Always process new documents
        if created:
            logger.info(f"New document created: {instance.id}, queuing AI processing")
            
            # Queue complete processing for new documents
            if hasattr(process_document_task, 'delay'):
                process_document_task.delay(str(instance.id))
            return
        
        # For existing documents, check if content changed significantly
        if _should_reprocess_document(instance):
            logger.info(f"Document {instance.id} content changed significantly, queuing AI processing")
            
            # Queue individual tasks for updated documents (more granular)
            if hasattr(generate_document_summary_task, 'delay'):
                generate_document_summary_task.delay(str(instance.id))
            
            if hasattr(extract_document_tags_task, 'delay'):
                extract_document_tags_task.delay(str(instance.id))
            
            if hasattr(generate_document_embedding_task, 'delay'):
                generate_document_embedding_task.delay(str(instance.id))
        
    except Exception as e:
        logger.error(f"Failed to queue AI processing for document {instance.id}: {str(e)}")


def _should_reprocess_document(document: Document) -> bool:
    """
    Determine if a document should be reprocessed based on content changes.
    
    Args:
        document: Document instance
        
    Returns:
        True if document should be reprocessed
    """
    try:
        # Get existing AI metadata
        ai_metadata = AIDocumentMetadata.objects.get(document=document)
        
        # Reprocess if never processed successfully
        if ai_metadata.processing_status != 'completed':
            return True
        
        # Reprocess if document was updated after last processing
        if ai_metadata.last_processed and document.updated_at > ai_metadata.last_processed:
            # Check if the content change is significant enough
            return _is_content_change_significant(document, ai_metadata)
        
        return False
        
    except AIDocumentMetadata.DoesNotExist:
        # No metadata exists, should process
        return True
    except Exception as e:
        logger.warning(f"Error checking reprocessing need for document {document.id}: {str(e)}")
        return False


def _is_content_change_significant(document: Document, ai_metadata: AIDocumentMetadata) -> bool:
    """
    Check if content changes are significant enough to warrant reprocessing.
    
    Args:
        document: Document instance
        ai_metadata: Existing AI metadata
        
    Returns:
        True if changes are significant
    """
    try:
        # Get current content length
        current_length = len(document.content_text) if document.content_text else 0
        
        # If we don't have previous content info, assume significant change
        if not hasattr(ai_metadata, 'content_length_at_processing'):
            return True
        
        # Calculate change percentage (placeholder - could be enhanced)
        # For now, consider changes significant if:
        # 1. Content length changed by more than 20%
        # 2. Title changed
        # 3. Document was published (status change)
        
        # Check title change (simple heuristic)
        if document.title != getattr(ai_metadata, 'processed_title', ''):
            return True
        
        # Check content length change
        previous_length = getattr(ai_metadata, 'processed_content_length', 0)
        if previous_length > 0:
            change_ratio = abs(current_length - previous_length) / previous_length
            if change_ratio > 0.2:  # 20% change threshold
                return True
        
        # Check if document was just published
        if (hasattr(document, 'status') and 
            document.status == 'published' and 
            getattr(ai_metadata, 'processed_status', '') != 'published'):
            return True
        
        return False
        
    except Exception as e:
        logger.warning(f"Error checking content significance for document {document.id}: {str(e)}")
        return True  # Err on the side of reprocessing


@receiver(post_delete, sender=Document)
def cleanup_ai_metadata_on_delete(sender, instance, **kwargs):
    """
    Clean up AI metadata when document is deleted.
    
    Args:
        sender: Document model class
        instance: Document instance being deleted
        **kwargs: Additional signal kwargs
    """
    try:
        # AI metadata should be automatically deleted due to CASCADE relationship
        # But we can log this for monitoring
        logger.info(f"Document {instance.id} deleted, AI metadata will be cleaned up automatically")
        
    except Exception as e:
        logger.error(f"Error during AI metadata cleanup for deleted document {instance.id}: {str(e)}")


# Signal for handling document content updates specifically
@receiver(post_save, sender=Document)
def update_embedding_on_content_change(sender, instance, created, **kwargs):
    """
    Update document embedding when content changes significantly.
    This is a separate signal to handle embedding updates with different priority.
    
    Args:
        sender: Document model class
        instance: Document instance
        created: Whether this is a new document
        **kwargs: Additional signal kwargs
    """
    # Skip if AI processing is disabled
    if not getattr(settings, 'AI_PROCESSING_ENABLED', True):
        return
    
    # Skip if tasks are not available
    if not TASKS_AVAILABLE:
        return
    
    # Skip for new documents (handled by main processing signal)
    if created:
        return
    
    try:
        # Check if we need to update embeddings
        from apps.ai_services.services.embedding_generator import get_embedding_generator
        
        embedding_generator = get_embedding_generator()
        needs_update = embedding_generator.update_embedding_if_needed(instance)
        
        if needs_update:
            logger.info(f"Queuing embedding update for document {instance.id}")
            
    except Exception as e:
        logger.error(f"Error checking embedding update need for document {instance.id}: {str(e)}")


# Health check signal for monitoring AI processing
def ai_processing_health_check():
    """
    Perform periodic health check of AI processing system.
    This can be called by management commands or monitoring systems.
    """
    try:
        if not TASKS_AVAILABLE:
            return {'status': 'error', 'message': 'AI tasks not available'}
        
        from apps.ai_services.tasks.document_tasks import health_check_ollama_task
        
        # Queue health check task
        if hasattr(health_check_ollama_task, 'delay'):
            result = health_check_ollama_task.delay()
            return {'status': 'queued', 'task_id': result.id}
        
        return {'status': 'error', 'message': 'Health check task not available'}
        
    except Exception as e:
        logger.error(f"AI processing health check failed: {str(e)}")
        return {'status': 'error', 'message': str(e)}
