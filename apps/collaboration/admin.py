"""
Admin configuration for collaboration app.
"""

from django.contrib import admin
from django.utils.html import format_html

from .models import (
    CollaborationActivity,
    CollaborationRoom,
    CollaborationSession,
    CursorPosition,
)


@admin.register(CollaborationRoom)
class CollaborationRoomAdmin(admin.ModelAdmin):
    """Admin interface for CollaborationRoom model."""

    list_display = [
        "name",
        "room_type",
        "status",
        "document",
        "team",
        "active_participants_count",
        "max_participants",
        "created_by",
        "last_activity",
    ]

    list_filter = [
        "room_type",
        "status",
        "is_public",
        "enable_voice",
        "enable_video",
        "enable_cursor_tracking",
        "team",
        "created_at",
    ]

    search_fields = [
        "name",
        "description",
        "document__title",
        "team__name",
        "created_by__username",
    ]

    readonly_fields = [
        "id",
        "active_participants_count",
        "is_full",
        "created_at",
        "updated_at",
        "last_activity",
    ]

    fieldsets = (
        (
            "Room Information",
            {
                "fields": (
                    "id",
                    "name",
                    "description",
                    "room_type",
                    "status",
                )
            },
        ),
        (
            "Associations",
            {
                "fields": (
                    "document",
                    "team",
                    "created_by",
                )
            },
        ),
        (
            "Settings",
            {
                "fields": (
                    "is_public",
                    "max_participants",
                    "allow_anonymous",
                )
            },
        ),
        (
            "Features",
            {
                "fields": (
                    "enable_voice",
                    "enable_video",
                    "enable_screen_share",
                    "enable_cursor_tracking",
                )
            },
        ),
        (
            "Metadata",
            {
                "fields": (
                    "settings",
                    "metadata",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Statistics",
            {
                "fields": (
                    "active_participants_count",
                    "is_full",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Timestamps",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                    "last_activity",
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
            .select_related("document", "team", "created_by")
        )


@admin.register(CollaborationSession)
class CollaborationSessionAdmin(admin.ModelAdmin):
    """Admin interface for CollaborationSession model."""

    list_display = [
        "user",
        "room",
        "status",
        "user_role",
        "is_active",
        "joined_at",
        "last_seen",
        "duration_display",
        "activity_count",
    ]

    list_filter = [
        "status",
        "user_role",
        "joined_at",
        "last_seen",
        "room__team",
    ]

    search_fields = [
        "user__username",
        "user__email",
        "room__name",
        "session_token",
    ]

    readonly_fields = [
        "id",
        "session_token",
        "is_active",
        "duration",
        "joined_at",
        "last_seen",
        "last_activity",
        "left_at",
        "total_time",
        "activity_count",
    ]

    fieldsets = (
        (
            "Session Information",
            {
                "fields": (
                    "id",
                    "room",
                    "user",
                    "session_token",
                )
            },
        ),
        (
            "Status",
            {
                "fields": (
                    "status",
                    "user_role",
                    "is_active",
                )
            },
        ),
        (
            "Connection",
            {
                "fields": (
                    "connection_id",
                    "ip_address",
                    "user_agent",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Metadata",
            {
                "fields": (
                    "client_info",
                    "session_data",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Activity Tracking",
            {
                "fields": (
                    "joined_at",
                    "last_seen",
                    "last_activity",
                    "left_at",
                    "duration",
                    "total_time",
                    "activity_count",
                )
            },
        ),
    )

    def get_queryset(self, request):
        """Optimize queryset with select_related."""
        return super().get_queryset(request).select_related("room", "user")

    def duration_display(self, obj):
        """Display session duration in a readable format."""
        duration = obj.duration
        if duration:
            hours, remainder = divmod(duration.total_seconds(), 3600)
            minutes, seconds = divmod(remainder, 60)
            return f"{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}"
        return "N/A"

    duration_display.short_description = "Duration"


@admin.register(CollaborationActivity)
class CollaborationActivityAdmin(admin.ModelAdmin):
    """Admin interface for CollaborationActivity model."""

    list_display = [
        "activity_type",
        "user",
        "room",
        "sequence_number",
        "server_timestamp",
        "is_applied",
        "is_broadcast",
    ]

    list_filter = [
        "activity_type",
        "is_applied",
        "is_broadcast",
        "server_timestamp",
        "room__team",
    ]

    search_fields = [
        "user__username",
        "room__name",
        "operation_id",
        "activity_type",
    ]

    readonly_fields = [
        "id",
        "operation_id",
        "server_timestamp",
        "sequence_number",
        "is_applied",
        "is_broadcast",
    ]

    fieldsets = (
        (
            "Activity Information",
            {
                "fields": (
                    "id",
                    "room",
                    "session",
                    "user",
                    "activity_type",
                )
            },
        ),
        (
            "Activity Data",
            {
                "fields": (
                    "activity_data",
                    "position",
                )
            },
        ),
        (
            "Operational Transform",
            {
                "fields": (
                    "operation",
                    "operation_id",
                    "parent_operation_id",
                    "document_version",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Timestamps",
            {
                "fields": (
                    "client_timestamp",
                    "server_timestamp",
                    "sequence_number",
                )
            },
        ),
        (
            "Status",
            {
                "fields": (
                    "is_applied",
                    "is_broadcast",
                )
            },
        ),
    )

    def get_queryset(self, request):
        """Optimize queryset with select_related."""
        return super().get_queryset(request).select_related("room", "session", "user")


@admin.register(CursorPosition)
class CursorPositionAdmin(admin.ModelAdmin):
    """Admin interface for CursorPosition model."""

    list_display = [
        "user",
        "room",
        "cursor_color_display",
        "is_visible",
        "last_updated",
    ]

    list_filter = [
        "is_visible",
        "last_updated",
        "room__team",
    ]

    search_fields = [
        "user__username",
        "room__name",
        "user_label",
    ]

    readonly_fields = [
        "id",
        "last_updated",
    ]

    fieldsets = (
        (
            "Position Information",
            {
                "fields": (
                    "id",
                    "session",
                    "room",
                    "user",
                )
            },
        ),
        (
            "Cursor Data",
            {
                "fields": (
                    "position",
                    "selection",
                )
            },
        ),
        (
            "Display",
            {
                "fields": (
                    "cursor_color",
                    "user_label",
                    "is_visible",
                )
            },
        ),
        ("Metadata", {"fields": ("last_updated",)}),
    )

    def get_queryset(self, request):
        """Optimize queryset with select_related."""
        return super().get_queryset(request).select_related("session", "room", "user")

    def cursor_color_display(self, obj):
        """Display cursor color as a colored box."""
        return format_html(
            '<div style="width: 20px; height: 20px; background-color: {}; '
            'border: 1px solid #ccc; display: inline-block;"></div> {}',
            obj.cursor_color,
            obj.cursor_color,
        )

    cursor_color_display.short_description = "Color"
