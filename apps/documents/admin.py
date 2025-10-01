"""
Admin configuration for documents app.
"""

from django.contrib import admin

from .models import (
    Document,
    DocumentComment,
    DocumentMedia,
    DocumentPermission,
    DocumentVersion,
)


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    """Admin interface for Document model."""

    list_display = [
        "title",
        "team",
        "document_type",
        "status",
        "created_by",
        "word_count",
        "created_at",
        "updated_at",
    ]
    list_filter = ["document_type", "status", "team", "created_at", "updated_at"]
    search_fields = ["title", "content", "created_by__username", "team__name"]
    readonly_fields = [
        "id",
        "word_count",
        "character_count",
        "media_count",
        "content_text",
        "created_at",
        "updated_at",
    ]
    filter_horizontal = []

    fieldsets = (
        (
            "Basic Information",
            {
                "fields": (
                    "title",
                    "content",
                    "document_type",
                    "status",
                    "is_public",
                )
            },
        ),
        (
            "Team & Ownership",
            {
                "fields": (
                    "team",
                    "created_by",
                    "updated_by",
                )
            },
        ),
        (
            "Metadata",
            {
                "fields": (
                    "tags",
                    "metadata",
                    "word_count",
                    "character_count",
                )
            },
        ),
        (
            "Timestamps",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )

    def get_queryset(self, request):
        """Optimize queryset with select_related."""
        return (
            super()
            .get_queryset(request)
            .select_related("team", "created_by", "updated_by")
        )


@admin.register(DocumentVersion)
class DocumentVersionAdmin(admin.ModelAdmin):
    """Admin interface for DocumentVersion model."""

    list_display = [
        "document",
        "version_number",
        "title",
        "created_by",
        "word_count",
        "created_at",
    ]
    list_filter = ["document", "created_by", "created_at"]
    search_fields = ["document__title", "title", "content", "created_by__username"]
    readonly_fields = ["id", "word_count", "character_count", "created_at"]

    fieldsets = (
        (
            "Version Information",
            {
                "fields": (
                    "document",
                    "version_number",
                    "title",
                    "content",
                    "change_summary",
                )
            },
        ),
        (
            "Metadata",
            {
                "fields": (
                    "word_count",
                    "character_count",
                    "created_by",
                    "created_at",
                )
            },
        ),
    )

    def get_queryset(self, request):
        """Optimize queryset with select_related."""
        return super().get_queryset(request).select_related("document", "created_by")


@admin.register(DocumentPermission)
class DocumentPermissionAdmin(admin.ModelAdmin):
    """Admin interface for DocumentPermission model."""

    list_display = [
        "document",
        "user",
        "permission_level",
        "granted_by",
        "granted_at",
    ]
    list_filter = ["permission_level", "granted_by", "granted_at"]
    search_fields = [
        "document__title",
        "user__username",
        "user__email",
        "granted_by__username",
    ]
    readonly_fields = ["id", "granted_at"]

    fieldsets = (
        (
            "Permission Details",
            {
                "fields": (
                    "document",
                    "user",
                    "permission_level",
                    "notes",
                )
            },
        ),
        (
            "Grant Information",
            {
                "fields": (
                    "granted_by",
                    "granted_at",
                )
            },
        ),
    )

    def get_queryset(self, request):
        """Optimize queryset with select_related."""
        return (
            super()
            .get_queryset(request)
            .select_related("document", "user", "granted_by")
        )


@admin.register(DocumentComment)
class DocumentCommentAdmin(admin.ModelAdmin):
    """Admin interface for DocumentComment model."""

    list_display = [
        "document",
        "user",
        "content_preview",
        "is_resolved",
        "parent_comment",
        "created_at",
    ]
    list_filter = ["is_resolved", "document", "user", "created_at"]
    search_fields = ["document__title", "user__username", "content"]
    readonly_fields = ["id", "created_at", "updated_at"]

    fieldsets = (
        (
            "Comment Details",
            {
                "fields": (
                    "document",
                    "user",
                    "content",
                    "parent_comment",
                )
            },
        ),
        (
            "Position",
            {
                "fields": (
                    "position_start",
                    "position_end",
                )
            },
        ),
        (
            "Status",
            {
                "fields": (
                    "is_resolved",
                    "resolved_by",
                    "resolved_at",
                )
            },
        ),
        (
            "Timestamps",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )

    def content_preview(self, obj):
        """Return a preview of the comment content."""
        return obj.content[:50] + "..." if len(obj.content) > 50 else obj.content

    content_preview.short_description = "Content Preview"

    def get_queryset(self, request):
        """Optimize queryset with select_related."""
        return (
            super()
            .get_queryset(request)
            .select_related("document", "user", "resolved_by", "parent_comment")
        )


@admin.register(DocumentMedia)
class DocumentMediaAdmin(admin.ModelAdmin):
    """Admin interface for DocumentMedia model."""

    list_display = [
        "filename",
        "document",
        "media_type",
        "usage_type",
        "file_size_formatted",
        "uploaded_by",
        "is_processed",
        "uploaded_at",
    ]
    list_filter = [
        "media_type",
        "usage_type",
        "is_processed",
        "uploaded_at",
    ]
    search_fields = [
        "filename",
        "original_filename",
        "document__title",
        "uploaded_by__username",
    ]
    readonly_fields = [
        "id",
        "file_size",
        "mime_type",
        "media_type",
        "width",
        "height",
        "duration",
        "file_url",
        "is_processed",
        "uploaded_at",
    ]

    fieldsets = (
        (
            "File Information",
            {
                "fields": (
                    "document",
                    "file",
                    "filename",
                    "original_filename",
                    "file_size",
                    "mime_type",
                    "media_type",
                )
            },
        ),
        (
            "Usage and Display",
            {
                "fields": (
                    "usage_type",
                    "position_data",
                    "alt_text",
                    "caption",
                )
            },
        ),
        (
            "Media Properties",
            {
                "fields": (
                    "width",
                    "height",
                    "duration",
                )
            },
        ),
        (
            "Processing Status",
            {
                "fields": (
                    "is_processed",
                    "processing_data",
                )
            },
        ),
        (
            "Upload Information",
            {
                "fields": (
                    "uploaded_by",
                    "uploaded_at",
                )
            },
        ),
    )

    def file_size_formatted(self, obj):
        """Return formatted file size."""
        if obj.file_size < 1024:
            return f"{obj.file_size} B"
        elif obj.file_size < 1024 * 1024:
            return f"{obj.file_size / 1024:.1f} KB"
        else:
            return f"{obj.file_size / (1024 * 1024):.1f} MB"

    file_size_formatted.short_description = "File Size"

    def get_queryset(self, request):
        """Optimize queryset with select_related."""
        return super().get_queryset(request).select_related("document", "uploaded_by")
