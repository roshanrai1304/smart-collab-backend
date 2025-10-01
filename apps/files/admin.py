"""
Admin configuration for files app.
"""

from django.contrib import admin
from django.utils.html import format_html

from .models import FilePermission, FileShare, FileUpload


@admin.register(FileUpload)
class FileUploadAdmin(admin.ModelAdmin):
    """Admin interface for FileUpload model."""

    list_display = [
        "original_name",
        "file_type",
        "human_readable_size",
        "team",
        "uploaded_by",
        "upload_status",
        "virus_scan_status",
        "is_public",
        "created_at",
    ]

    list_filter = [
        "file_type",
        "upload_status",
        "virus_scan_status",
        "is_public",
        "is_image",
        "team",
        "created_at",
    ]

    search_fields = [
        "original_name",
        "file_name",
        "description",
        "uploaded_by__username",
        "uploaded_by__email",
        "team__name",
    ]

    readonly_fields = [
        "id",
        "file_name",
        "file_size",
        "human_readable_size",
        "mime_type",
        "file_type",
        "file_extension",
        "is_image",
        "image_width",
        "image_height",
        "file_url",
        "is_safe",
        "created_at",
        "updated_at",
        "file_preview",
    ]

    fieldsets = (
        (
            "File Information",
            {
                "fields": (
                    "id",
                    "original_name",
                    "file_name",
                    "file",
                    "file_size",
                    "human_readable_size",
                    "mime_type",
                    "file_type",
                    "file_extension",
                    "file_url",
                    "file_preview",
                )
            },
        ),
        (
            "Content",
            {
                "fields": (
                    "description",
                    "tags",
                    "metadata",
                )
            },
        ),
        (
            "Image Metadata",
            {
                "fields": (
                    "is_image",
                    "image_width",
                    "image_height",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Associations",
            {
                "fields": (
                    "team",
                    "uploaded_by",
                    "document",
                )
            },
        ),
        (
            "Status & Security",
            {
                "fields": (
                    "upload_status",
                    "processing_info",
                    "virus_scan_status",
                    "is_safe",
                    "is_public",
                )
            },
        ),
        (
            "Timestamps",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                ),
                "classes": ("collapse",),
            },
        ),
    )

    def get_queryset(self, request):
        """Optimize queryset with select_related."""
        return (
            super()
            .get_queryset(request)
            .select_related("team", "uploaded_by", "document")
        )

    def file_preview(self, obj):
        """Display file preview for images."""
        if obj.is_image and obj.file_url:
            return format_html(
                '<img src="{}" style="max-width: 200px; max-height: 200px;" />',
                obj.file_url,
            )
        return "No preview available"

    file_preview.short_description = "Preview"


@admin.register(FilePermission)
class FilePermissionAdmin(admin.ModelAdmin):
    """Admin interface for FilePermission model."""

    list_display = [
        "file",
        "user",
        "permission_level",
        "granted_by",
        "granted_at",
    ]

    list_filter = [
        "permission_level",
        "granted_at",
        "file__team",
    ]

    search_fields = [
        "file__original_name",
        "user__username",
        "user__email",
        "granted_by__username",
    ]

    readonly_fields = [
        "id",
        "granted_at",
    ]

    fieldsets = (
        (
            "Permission Details",
            {
                "fields": (
                    "id",
                    "file",
                    "user",
                    "permission_level",
                )
            },
        ),
        (
            "Grant Information",
            {
                "fields": (
                    "granted_by",
                    "granted_at",
                    "notes",
                )
            },
        ),
    )

    def get_queryset(self, request):
        """Optimize queryset with select_related."""
        return (
            super().get_queryset(request).select_related("file", "user", "granted_by")
        )


@admin.register(FileShare)
class FileShareAdmin(admin.ModelAdmin):
    """Admin interface for FileShare model."""

    list_display = [
        "file",
        "share_type",
        "password_protected",
        "access_count",
        "download_count",
        "is_active",
        "created_by",
        "created_at",
    ]

    list_filter = [
        "share_type",
        "password_protected",
        "created_at",
        "expires_at",
    ]

    search_fields = [
        "file__original_name",
        "share_token",
        "created_by__username",
    ]

    readonly_fields = [
        "id",
        "share_token",
        "access_count",
        "download_count",
        "last_accessed",
        "created_at",
        "is_expired",
        "is_download_limit_reached",
        "is_active",
        "share_url_display",
    ]

    fieldsets = (
        (
            "Share Information",
            {
                "fields": (
                    "id",
                    "file",
                    "share_token",
                    "share_type",
                    "share_url_display",
                )
            },
        ),
        (
            "Access Control",
            {
                "fields": (
                    "password_protected",
                    "password_hash",
                    "max_downloads",
                    "expires_at",
                )
            },
        ),
        (
            "Statistics",
            {
                "fields": (
                    "access_count",
                    "download_count",
                    "last_accessed",
                    "is_expired",
                    "is_download_limit_reached",
                    "is_active",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Metadata",
            {
                "fields": (
                    "created_by",
                    "created_at",
                )
            },
        ),
        (
            "Access Log",
            {
                "fields": ("access_log",),
                "classes": ("collapse",),
            },
        ),
    )

    def get_queryset(self, request):
        """Optimize queryset with select_related."""
        return super().get_queryset(request).select_related("file", "created_by")

    def share_url_display(self, obj):
        """Display the share URL."""
        return format_html(
            '<a href="/api/v1/files/share/{}/" target="_blank">/api/v1/files/share/{}/</a>',
            obj.share_token,
            obj.share_token,
        )

    share_url_display.short_description = "Share URL"
