"""
Serializers for AI Services API.

Handles serialization/deserialization of AI-related data for the REST API.
"""

from rest_framework import serializers
from apps.ai_services.models import AIDocumentMetadata, AIProcessingQueue, AISuggestionsCache


class AIDocumentMetadataSerializer(serializers.ModelSerializer):
    """
    Serializer for AI document metadata.
    """
    
    document_id = serializers.CharField(source='document.id', read_only=True)
    document_title = serializers.CharField(source='document.title', read_only=True)
    organization_name = serializers.CharField(source='organization.name', read_only=True)
    
    class Meta:
        model = AIDocumentMetadata
        fields = [
            'id',
            'document_id',
            'document_title',
            'organization_name',
            'processing_status',
            'last_processed',
            'processing_version',
            'model_version',
            'summary',
            'key_points',
            'auto_tags',
            'sentiment_score',
            'readability_score',
            'detected_content_type',
            'embedding_model',
            'confidence_scores',
            'processing_time_ms',
            'error_message',
            'retry_count',
            'created_at',
            'updated_at'
        ]
        read_only_fields = [
            'id',
            'document_id',
            'document_title',
            'organization_name',
            'processing_status',
            'last_processed',
            'processing_version',
            'model_version',
            'summary',
            'key_points',
            'auto_tags',
            'sentiment_score',
            'readability_score',
            'detected_content_type',
            'embedding_model',
            'confidence_scores',
            'processing_time_ms',
            'error_message',
            'retry_count',
            'created_at',
            'updated_at'
        ]


class AIProcessingQueueSerializer(serializers.ModelSerializer):
    """
    Serializer for AI processing queue entries.
    """
    
    document_id = serializers.CharField(source='document.id', read_only=True)
    document_title = serializers.CharField(source='document.title', read_only=True)
    duration_seconds = serializers.SerializerMethodField()
    
    class Meta:
        model = AIProcessingQueue
        fields = [
            'id',
            'document_id',
            'document_title',
            'task_type',
            'priority',
            'status',
            'celery_task_id',
            'input_data',
            'output_data',
            'error_message',
            'retry_count',
            'processing_time_ms',
            'duration_seconds',
            'created_at',
            'started_at',
            'completed_at'
        ]
        read_only_fields = [
            'id',
            'document_id',
            'document_title',
            'task_type',
            'priority',
            'status',
            'celery_task_id',
            'input_data',
            'output_data',
            'error_message',
            'retry_count',
            'processing_time_ms',
            'duration_seconds',
            'created_at',
            'started_at',
            'completed_at'
        ]
    
    def get_duration_seconds(self, obj):
        """Calculate task duration in seconds."""
        if obj.duration:
            return obj.duration.total_seconds()
        return None


class DocumentSummarySerializer(serializers.Serializer):
    """
    Serializer for document summary data.
    """
    
    document_id = serializers.UUIDField()
    title = serializers.CharField()
    summary = serializers.CharField(allow_null=True)
    key_points = serializers.ListField(
        child=serializers.DictField(),
        default=list
    )
    processing_status = serializers.CharField()
    last_processed = serializers.DateTimeField(allow_null=True)


class SemanticSearchSerializer(serializers.Serializer):
    """
    Serializer for semantic search requests.
    """
    
    query = serializers.CharField(
        min_length=3,
        max_length=500,
        help_text="Search query (3-500 characters)"
    )
    team_id = serializers.UUIDField(
        required=False,
        allow_null=True,
        help_text="Optional team ID to limit search scope"
    )
    limit = serializers.IntegerField(
        default=10,
        min_value=1,
        max_value=50,
        help_text="Maximum number of results (1-50)"
    )
    similarity_threshold = serializers.FloatField(
        default=0.7,
        min_value=0.0,
        max_value=1.0,
        help_text="Minimum similarity score (0.0-1.0)"
    )


class SemanticSearchResultSerializer(serializers.Serializer):
    """
    Serializer for semantic search results.
    """
    
    document_id = serializers.UUIDField()
    title = serializers.CharField()
    content_preview = serializers.CharField(allow_null=True)
    summary = serializers.CharField(allow_null=True)
    tags = serializers.ListField(child=serializers.CharField(), default=list)
    content_type = serializers.CharField(allow_null=True)
    similarity_score = serializers.FloatField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()


class SimilarDocumentSerializer(serializers.Serializer):
    """
    Serializer for similar document results.
    """
    
    document_id = serializers.UUIDField()
    title = serializers.CharField()
    content_preview = serializers.CharField(allow_null=True)
    summary = serializers.CharField(allow_null=True)
    tags = serializers.ListField(child=serializers.CharField(), default=list)
    content_type = serializers.CharField(allow_null=True)
    similarity_score = serializers.FloatField()


class AISuggestionsCacheSerializer(serializers.ModelSerializer):
    """
    Serializer for AI suggestions cache entries.
    """
    
    is_expired = serializers.SerializerMethodField()
    
    class Meta:
        model = AISuggestionsCache
        fields = [
            'id',
            'content_hash',
            'suggestion_type',
            'input_text',
            'suggestions',
            'model_version',
            'confidence_score',
            'usage_count',
            'last_used',
            'expires_at',
            'is_expired',
            'created_at'
        ]
        read_only_fields = [
            'id',
            'content_hash',
            'suggestion_type',
            'input_text',
            'suggestions',
            'model_version',
            'confidence_score',
            'usage_count',
            'last_used',
            'expires_at',
            'is_expired',
            'created_at'
        ]
    
    def get_is_expired(self, obj):
        """Check if cache entry is expired."""
        return obj.is_expired()


class BatchProcessingRequestSerializer(serializers.Serializer):
    """
    Serializer for batch processing requests.
    """
    
    document_ids = serializers.ListField(
        child=serializers.UUIDField(),
        min_length=1,
        max_length=100,
        help_text="List of document IDs to process (1-100)"
    )
    force_reprocess = serializers.BooleanField(
        default=False,
        help_text="Force reprocessing even if already processed"
    )
    processing_types = serializers.ListField(
        child=serializers.ChoiceField(
            choices=['summarize', 'tag', 'embed', 'analyze', 'all']
        ),
        default=['all'],
        help_text="Types of processing to perform"
    )


class AIHealthCheckSerializer(serializers.Serializer):
    """
    Serializer for AI system health check responses.
    """
    
    overall_status = serializers.CharField()
    ollama = serializers.DictField()
    processing_stats = serializers.DictField()
    queue_stats = serializers.DictField()
    error = serializers.CharField(required=False, allow_null=True)


class TaskStatusSerializer(serializers.Serializer):
    """
    Serializer for Celery task status responses.
    """
    
    task_id = serializers.CharField()
    status = serializers.CharField()
    result = serializers.DictField(required=False, allow_null=True)
    error = serializers.CharField(required=False, allow_null=True)
    progress = serializers.DictField(required=False, allow_null=True)
    
    
class EmbeddingStatsSerializer(serializers.Serializer):
    """
    Serializer for embedding statistics.
    """
    
    total_documents = serializers.IntegerField()
    with_embeddings = serializers.IntegerField()
    processing = serializers.IntegerField()
    failed = serializers.IntegerField()
    completion_rate = serializers.FloatField()
    embedding_model = serializers.CharField()


class ContentAnalysisSerializer(serializers.Serializer):
    """
    Serializer for content analysis requests and responses.
    """
    
    content = serializers.CharField(
        min_length=10,
        max_length=50000,
        help_text="Text content to analyze (10-50000 characters)"
    )
    analysis_types = serializers.ListField(
        child=serializers.ChoiceField(
            choices=['summary', 'tags', 'sentiment', 'content_type', 'key_points']
        ),
        default=['summary', 'tags'],
        help_text="Types of analysis to perform"
    )
    max_summary_length = serializers.IntegerField(
        default=200,
        min_value=50,
        max_value=1000,
        help_text="Maximum summary length in words"
    )
    max_tags = serializers.IntegerField(
        default=10,
        min_value=1,
        max_value=20,
        help_text="Maximum number of tags to extract"
    )


class ContentAnalysisResultSerializer(serializers.Serializer):
    """
    Serializer for content analysis results.
    """
    
    summary = serializers.CharField(required=False, allow_null=True)
    tags = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        default=list
    )
    sentiment_score = serializers.FloatField(required=False, allow_null=True)
    content_type = serializers.CharField(required=False, allow_null=True)
    key_points = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        default=list
    )
    confidence_scores = serializers.DictField(required=False, default=dict)
    processing_time_ms = serializers.IntegerField(required=False)
