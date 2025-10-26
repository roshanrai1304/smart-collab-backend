"""
AI Services API views for Smart Collaborative Backend.

Provides REST API endpoints for AI functionality:
- Document analysis and summarization
- Semantic search
- AI metadata management
- Processing status and health checks
"""

import logging
from typing import Dict, Any

from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.documents.models import Document
from apps.ai_services.models import AIDocumentMetadata, AIProcessingQueue
from apps.ai_services.serializers import (
    AIDocumentMetadataSerializer,
    AIProcessingQueueSerializer,
    DocumentSummarySerializer,
    SemanticSearchSerializer
)
from apps.ai_services.services.document_processor import get_document_processor
from apps.ai_services.services.embedding_generator import get_embedding_generator
from apps.ai_services.services.ollama_client import get_ollama_client
from apps.ai_services.tasks.document_tasks import (
    process_document_task,
    generate_document_summary_task,
    extract_document_tags_task,
    generate_document_embedding_task,
    batch_process_documents_task
)

logger = logging.getLogger(__name__)


class AIDocumentMetadataViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for AI document metadata.
    
    Provides read-only access to AI-generated document metadata including
    summaries, tags, embeddings, and processing status.
    """
    
    serializer_class = AIDocumentMetadataSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """Filter metadata based on user's document access."""
        user = self.request.user
        
        # Get documents the user has access to
        accessible_documents = Document.objects.filter(
            team__memberships__user=user,
            team__memberships__status='active'
        )
        
        return AIDocumentMetadata.objects.filter(
            document__in=accessible_documents
        ).select_related('document', 'organization')
    
    @action(detail=True, methods=['post'])
    def reprocess(self, request, pk=None):
        """
        Trigger reprocessing of AI metadata for a document.
        
        POST /ai/metadata/{id}/reprocess/
        """
        try:
            metadata = self.get_object()
            
            # Check if user has write access to the document
            if not metadata.document.can_write(request.user):
                return Response(
                    {'error': 'Permission denied'}, 
                    status=status.HTTP_403_FORBIDDEN
                )
            
            # Queue reprocessing task
            task_result = process_document_task.delay(
                str(metadata.document.id), 
                force_reprocess=True
            )
            
            return Response({
                'message': 'Reprocessing queued successfully',
                'task_id': task_result.id,
                'document_id': str(metadata.document.id)
            })
            
        except Exception as e:
            logger.error(f"Failed to queue reprocessing: {str(e)}")
            return Response(
                {'error': 'Failed to queue reprocessing'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class DocumentSummaryView(APIView):
    """
    API view for document summarization.
    """
    
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request, document_id):
        """
        Get existing summary for a document.
        
        GET /ai/documents/{document_id}/summary/
        """
        try:
            document = get_object_or_404(Document, id=document_id)
            
            # Check permissions
            if not document.can_read(request.user):
                return Response(
                    {'error': 'Permission denied'}, 
                    status=status.HTTP_403_FORBIDDEN
                )
            
            # Get AI metadata
            try:
                ai_metadata = AIDocumentMetadata.objects.get(document=document)
                serializer = DocumentSummarySerializer({
                    'document_id': str(document.id),
                    'title': document.title,
                    'summary': ai_metadata.summary,
                    'key_points': ai_metadata.key_points,
                    'processing_status': ai_metadata.processing_status,
                    'last_processed': ai_metadata.last_processed
                })
                return Response(serializer.data)
                
            except AIDocumentMetadata.DoesNotExist:
                return Response({
                    'document_id': str(document.id),
                    'title': document.title,
                    'summary': None,
                    'key_points': [],
                    'processing_status': 'not_processed',
                    'last_processed': None
                })
                
        except Exception as e:
            logger.error(f"Error getting document summary: {str(e)}")
            return Response(
                {'error': 'Failed to get summary'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def post(self, request, document_id):
        """
        Generate or regenerate summary for a document.
        
        POST /ai/documents/{document_id}/summary/
        {
            "force_regenerate": false,
            "max_length": 200
        }
        """
        try:
            document = get_object_or_404(Document, id=document_id)
            
            # Check permissions
            if not document.can_read(request.user):
                return Response(
                    {'error': 'Permission denied'}, 
                    status=status.HTTP_403_FORBIDDEN
                )
            
            # Get parameters
            force_regenerate = request.data.get('force_regenerate', False)
            max_length = request.data.get('max_length', 200)
            
            # Validate max_length
            if not isinstance(max_length, int) or max_length < 50 or max_length > 1000:
                return Response(
                    {'error': 'max_length must be between 50 and 1000'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Check if summary already exists and force_regenerate is False
            if not force_regenerate:
                try:
                    ai_metadata = AIDocumentMetadata.objects.get(document=document)
                    if ai_metadata.summary and ai_metadata.processing_status == 'completed':
                        return Response({
                            'message': 'Summary already exists',
                            'document_id': str(document.id),
                            'summary': ai_metadata.summary,
                            'use_force_regenerate': 'Set force_regenerate=true to regenerate'
                        })
                except AIDocumentMetadata.DoesNotExist:
                    pass
            
            # Queue summary generation task
            task_result = generate_document_summary_task.delay(str(document.id))
            
            return Response({
                'message': 'Summary generation queued',
                'task_id': task_result.id,
                'document_id': str(document.id),
                'estimated_completion': '30-60 seconds'
            }, status=status.HTTP_202_ACCEPTED)
            
        except Exception as e:
            logger.error(f"Error generating document summary: {str(e)}")
            return Response(
                {'error': 'Failed to generate summary'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class SemanticSearchView(APIView):
    """
    API view for semantic document search.
    """
    
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        """
        Perform semantic search across documents.
        
        POST /ai/search/semantic/
        {
            "query": "search query",
            "team_id": "optional-team-id",
            "limit": 10,
            "similarity_threshold": 0.7
        }
        """
        try:
            serializer = SemanticSearchSerializer(data=request.data)
            if not serializer.is_valid():
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
            query = serializer.validated_data['query']
            team_id = serializer.validated_data.get('team_id')
            limit = serializer.validated_data.get('limit', 10)
            similarity_threshold = serializer.validated_data.get('similarity_threshold', 0.7)
            
            # Get user's organization for filtering
            user_teams = request.user.team_memberships.filter(status='active')
            if not user_teams.exists():
                return Response(
                    {'error': 'User is not a member of any team'}, 
                    status=status.HTTP_403_FORBIDDEN
                )
            
            # If team_id specified, verify user has access
            if team_id:
                if not user_teams.filter(team_id=team_id).exists():
                    return Response(
                        {'error': 'Permission denied for specified team'}, 
                        status=status.HTTP_403_FORBIDDEN
                    )
            
            # Perform semantic search
            embedding_generator = get_embedding_generator()
            
            if team_id:
                results = embedding_generator.semantic_search(
                    query=query,
                    team_id=team_id,
                    limit=limit,
                    similarity_threshold=similarity_threshold
                )
            else:
                # Search across all user's teams
                organization_id = user_teams.first().team.organization.id
                results = embedding_generator.semantic_search(
                    query=query,
                    organization_id=str(organization_id),
                    limit=limit,
                    similarity_threshold=similarity_threshold
                )
            
            return Response({
                'query': query,
                'results': results,
                'total_results': len(results),
                'search_type': 'semantic'
            })
            
        except Exception as e:
            logger.error(f"Semantic search failed: {str(e)}")
            return Response(
                {'error': 'Search failed'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class SimilarDocumentsView(APIView):
    """
    API view for finding similar documents.
    """
    
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request, document_id):
        """
        Find documents similar to the specified document.
        
        GET /ai/documents/{document_id}/similar/?limit=5&threshold=0.6
        """
        try:
            document = get_object_or_404(Document, id=document_id)
            
            # Check permissions
            if not document.can_read(request.user):
                return Response(
                    {'error': 'Permission denied'}, 
                    status=status.HTTP_403_FORBIDDEN
                )
            
            # Get parameters
            limit = int(request.query_params.get('limit', 5))
            threshold = float(request.query_params.get('threshold', 0.6))
            
            # Validate parameters
            if limit < 1 or limit > 20:
                return Response(
                    {'error': 'limit must be between 1 and 20'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if threshold < 0.0 or threshold > 1.0:
                return Response(
                    {'error': 'threshold must be between 0.0 and 1.0'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Find similar documents
            embedding_generator = get_embedding_generator()
            similar_docs = embedding_generator.find_similar_documents(
                document_id=str(document.id),
                limit=limit,
                similarity_threshold=threshold
            )
            
            return Response({
                'reference_document': {
                    'id': str(document.id),
                    'title': document.title
                },
                'similar_documents': similar_docs,
                'total_found': len(similar_docs)
            })
            
        except ValueError as e:
            return Response(
                {'error': f'Invalid parameter: {str(e)}'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Similar documents search failed: {str(e)}")
            return Response(
                {'error': 'Similar documents search failed'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class AIProcessingQueueViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for monitoring AI processing queue.
    """
    
    serializer_class = AIProcessingQueueSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """Filter queue entries based on user's document access."""
        user = self.request.user
        
        # Get documents the user has access to
        accessible_documents = Document.objects.filter(
            team__memberships__user=user,
            team__memberships__status='active'
        )
        
        return AIProcessingQueue.objects.filter(
            document__in=accessible_documents
        ).select_related('document').order_by('-created_at')


class AIHealthCheckView(APIView):
    """
    API view for AI system health checks.
    """
    
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """
        Get AI system health status.
        
        GET /ai/health/
        """
        try:
            # Check Ollama client
            ollama_client = get_ollama_client()
            ollama_healthy = ollama_client.health_check()
            
            # Get processing statistics
            total_metadata = AIDocumentMetadata.objects.count()
            completed = AIDocumentMetadata.objects.filter(processing_status='completed').count()
            processing = AIDocumentMetadata.objects.filter(processing_status='processing').count()
            failed = AIDocumentMetadata.objects.filter(processing_status='failed').count()
            
            # Get queue statistics
            queued_tasks = AIProcessingQueue.objects.filter(status='queued').count()
            processing_tasks = AIProcessingQueue.objects.filter(status='processing').count()
            
            health_data = {
                'overall_status': 'healthy' if ollama_healthy else 'unhealthy',
                'ollama': {
                    'status': 'healthy' if ollama_healthy else 'unhealthy',
                    'server_url': ollama_client.base_url,
                    'default_model': ollama_client.default_model,
                    'embedding_model': ollama_client.embedding_model
                },
                'processing_stats': {
                    'total_documents': total_metadata,
                    'completed': completed,
                    'processing': processing,
                    'failed': failed,
                    'completion_rate': (completed / total_metadata * 100) if total_metadata > 0 else 0
                },
                'queue_stats': {
                    'queued_tasks': queued_tasks,
                    'processing_tasks': processing_tasks
                }
            }
            
            # Add available models if Ollama is healthy
            if ollama_healthy:
                try:
                    models = ollama_client.list_models()
                    health_data['ollama']['available_models'] = [
                        model.get('name', 'unknown') for model in models
                    ]
                except Exception:
                    health_data['ollama']['available_models'] = []
            
            return Response(health_data)
            
        except Exception as e:
            logger.error(f"Health check failed: {str(e)}")
            return Response(
                {
                    'overall_status': 'error',
                    'error': str(e)
                }, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class BatchProcessingView(APIView):
    """
    API view for batch processing operations.
    """
    
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        """
        Queue batch processing for multiple documents.
        
        POST /ai/batch/process/
        {
            "document_ids": ["id1", "id2", "id3"],
            "force_reprocess": false,
            "processing_types": ["summarize", "tag", "embed"]
        }
        """
        try:
            document_ids = request.data.get('document_ids', [])
            force_reprocess = request.data.get('force_reprocess', False)
            processing_types = request.data.get('processing_types', ['all'])
            
            # Validate input
            if not isinstance(document_ids, list) or not document_ids:
                return Response(
                    {'error': 'document_ids must be a non-empty list'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if len(document_ids) > 100:
                return Response(
                    {'error': 'Maximum 100 documents per batch'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Verify user has access to all documents
            accessible_documents = Document.objects.filter(
                id__in=document_ids,
                team__memberships__user=request.user,
                team__memberships__status='active'
            )
            
            accessible_ids = [str(doc.id) for doc in accessible_documents]
            inaccessible_ids = [doc_id for doc_id in document_ids if doc_id not in accessible_ids]
            
            if inaccessible_ids:
                return Response(
                    {
                        'error': 'Permission denied for some documents',
                        'inaccessible_documents': inaccessible_ids
                    }, 
                    status=status.HTTP_403_FORBIDDEN
                )
            
            # Queue batch processing
            task_result = batch_process_documents_task.delay(
                document_ids=accessible_ids,
                force_reprocess=force_reprocess
            )
            
            return Response({
                'message': 'Batch processing queued',
                'task_id': task_result.id,
                'document_count': len(accessible_ids),
                'estimated_completion': f'{len(accessible_ids) * 30}-{len(accessible_ids) * 60} seconds'
            }, status=status.HTTP_202_ACCEPTED)
            
        except Exception as e:
            logger.error(f"Batch processing failed: {str(e)}")
            return Response(
                {'error': 'Batch processing failed'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
