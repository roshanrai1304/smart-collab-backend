"""
URLs for AI Services app.

Provides REST API endpoints for AI functionality including:
- Document analysis and summarization
- Semantic search
- AI metadata management
- Processing status and health checks
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from apps.ai_services.views import (
    AIDocumentMetadataViewSet,
    AIProcessingQueueViewSet,
    DocumentSummaryView,
    SemanticSearchView,
    SimilarDocumentsView,
    AIHealthCheckView,
    BatchProcessingView
)

# Create router for viewsets
router = DefaultRouter()
router.register(r'metadata', AIDocumentMetadataViewSet, basename='ai-metadata')
router.register(r'queue', AIProcessingQueueViewSet, basename='ai-queue')

app_name = 'ai_services'

urlpatterns = [
    # Router URLs (viewsets)
    path('', include(router.urls)),
    
    # Document-specific AI endpoints
    path('documents/<uuid:document_id>/summary/', 
         DocumentSummaryView.as_view(), 
         name='document-summary'),
    
    path('documents/<uuid:document_id>/similar/', 
         SimilarDocumentsView.as_view(), 
         name='similar-documents'),
    
    # Search endpoints
    path('search/semantic/', 
         SemanticSearchView.as_view(), 
         name='semantic-search'),
    
    # System endpoints
    path('health/', 
         AIHealthCheckView.as_view(), 
         name='health-check'),
    
    path('batch/process/', 
         BatchProcessingView.as_view(), 
         name='batch-process'),
]
