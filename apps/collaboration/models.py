"""
Real-time collaboration models for Smart Collaborative Backend.

This module defines the collaboration structure:
- CollaborationRoom (document collaboration spaces)
- CollaborationSession (user sessions in rooms)
- CollaborationActivity (real-time activities)
- CursorPosition (user cursor tracking)
- DocumentChange (operational transforms)
"""

import uuid
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.documents.models import Document
from apps.organizations.models import Team


class CollaborationRoom(models.Model):
    """
    Collaboration room for real-time document editing.
    Each document can have multiple collaboration rooms for different purposes.
    """

    ROOM_TYPES = [
        ("document", "Document Editing"),
        ("discussion", "Discussion"),
        ("review", "Review Session"),
        ("presentation", "Presentation"),
    ]

    ROOM_STATUS = [
        ("active", "Active"),
        ("paused", "Paused"),
        ("archived", "Archived"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Room configuration
    name = models.CharField(max_length=255, help_text="Room display name")
    description = models.TextField(blank=True, help_text="Room description")
    room_type = models.CharField(max_length=20, choices=ROOM_TYPES, default="document")
    status = models.CharField(max_length=20, choices=ROOM_STATUS, default="active")

    # Associations
    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name="collaboration_rooms",
        help_text="Associated document",
    )
    team = models.ForeignKey(
        Team, on_delete=models.CASCADE, related_name="collaboration_rooms"
    )
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="created_rooms"
    )

    # Room settings
    is_public = models.BooleanField(
        default=True, help_text="Public rooms are visible to all team members"
    )
    max_participants = models.PositiveIntegerField(
        default=50, help_text="Maximum concurrent participants"
    )
    allow_anonymous = models.BooleanField(
        default=False, help_text="Allow anonymous participants"
    )

    # Collaboration features
    enable_voice = models.BooleanField(default=False, help_text="Enable voice chat")
    enable_video = models.BooleanField(default=False, help_text="Enable video chat")
    enable_screen_share = models.BooleanField(
        default=True, help_text="Enable screen sharing"
    )
    enable_cursor_tracking = models.BooleanField(
        default=True, help_text="Show user cursors"
    )

    # Room metadata
    settings = models.JSONField(
        default=dict, blank=True, help_text="Additional room settings"
    )
    metadata = models.JSONField(default=dict, blank=True, help_text="Room metadata")

    # Timestamps
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    last_activity = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "collaboration_rooms"
        ordering = ["-last_activity"]
        indexes = [
            models.Index(fields=["document"], name="idx_room_document"),
            models.Index(fields=["team"], name="idx_room_team"),
            models.Index(fields=["status"], name="idx_room_status"),
            models.Index(fields=["room_type"], name="idx_room_type"),
            models.Index(fields=["created_by"], name="idx_room_creator"),
            models.Index(fields=["last_activity"], name="idx_room_activity"),
        ]

    def __str__(self):
        return f"{self.name} ({self.document.title})"

    def clean(self):
        """Validate room data."""
        if self.max_participants < 1:
            raise ValidationError("Maximum participants must be at least 1")

        if self.max_participants > 1000:
            raise ValidationError("Maximum participants cannot exceed 1000")

    @property
    def active_participants_count(self):
        """Get count of currently active participants."""
        return self.sessions.filter(
            status="active", last_seen__gte=timezone.now() - timedelta(minutes=5)
        ).count()

    @property
    def is_full(self):
        """Check if room is at capacity."""
        return self.active_participants_count >= self.max_participants

    def can_join(self, user):
        """Check if user can join this room."""
        # Check if room is active
        if self.status != "active":
            return False

        # Check capacity
        if self.is_full:
            return False

        # Check team membership (unless anonymous allowed)
        if not self.allow_anonymous:
            if not self.team.memberships.filter(user=user, status="active").exists():
                return False

        # Check document access
        if not self.document.can_read(user):
            return False

        return True

    def get_active_sessions(self):
        """Get currently active sessions."""
        return self.sessions.filter(
            status="active", last_seen__gte=timezone.now() - timedelta(minutes=5)
        ).select_related("user")

    def update_activity(self):
        """Update last activity timestamp."""
        self.last_activity = timezone.now()
        self.save(update_fields=["last_activity"])


class CollaborationSession(models.Model):
    """
    User session within a collaboration room.
    Tracks user presence and session metadata.
    """

    SESSION_STATUS = [
        ("active", "Active"),
        ("idle", "Idle"),
        ("disconnected", "Disconnected"),
    ]

    USER_ROLES = [
        ("viewer", "Viewer"),
        ("editor", "Editor"),
        ("moderator", "Moderator"),
        ("presenter", "Presenter"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Session identification
    room = models.ForeignKey(
        CollaborationRoom, on_delete=models.CASCADE, related_name="sessions"
    )
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="collaboration_sessions"
    )
    session_token = models.CharField(
        max_length=64, unique=True, help_text="Unique session token"
    )

    # Session status
    status = models.CharField(max_length=20, choices=SESSION_STATUS, default="active")
    user_role = models.CharField(max_length=20, choices=USER_ROLES, default="editor")

    # Connection info
    connection_id = models.CharField(
        max_length=128, blank=True, help_text="WebSocket connection ID"
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)

    # Session metadata
    client_info = models.JSONField(
        default=dict, blank=True, help_text="Client browser/device info"
    )
    session_data = models.JSONField(
        default=dict, blank=True, help_text="Session-specific data"
    )

    # Activity tracking
    joined_at = models.DateTimeField(default=timezone.now)
    last_seen = models.DateTimeField(default=timezone.now)
    last_activity = models.DateTimeField(default=timezone.now)
    left_at = models.DateTimeField(null=True, blank=True)

    # Statistics
    total_time = models.DurationField(
        default=timedelta, help_text="Total time in session"
    )
    activity_count = models.PositiveIntegerField(
        default=0, help_text="Number of activities performed"
    )

    class Meta:
        db_table = "collaboration_sessions"
        unique_together = ["room", "user"]
        ordering = ["-last_activity"]
        indexes = [
            models.Index(fields=["room", "status"], name="idx_session_room_status"),
            models.Index(fields=["user"], name="idx_session_user"),
            models.Index(fields=["session_token"], name="idx_session_token"),
            models.Index(fields=["status"], name="idx_session_status"),
            models.Index(fields=["last_seen"], name="idx_session_last_seen"),
        ]

    def __str__(self):
        return f"{self.user.username} in {self.room.name}"

    def save(self, *args, **kwargs):
        """Override save to generate session token."""
        if not self.session_token:
            import secrets

            self.session_token = secrets.token_urlsafe(32)
        super().save(*args, **kwargs)

    @property
    def is_active(self):
        """Check if session is currently active."""
        if self.status != "active":
            return False

        # Consider active if seen within last 5 minutes
        return self.last_seen >= timezone.now() - timedelta(minutes=5)

    @property
    def duration(self):
        """Get session duration."""
        if self.left_at:
            return self.left_at - self.joined_at
        return timezone.now() - self.joined_at

    def update_activity(self, activity_type=None):
        """Update session activity."""
        now = timezone.now()
        self.last_seen = now
        self.last_activity = now
        self.activity_count += 1

        # Update total time
        if self.status == "active":
            self.total_time = self.duration

        self.save(
            update_fields=["last_seen", "last_activity", "activity_count", "total_time"]
        )

        # Update room activity
        self.room.update_activity()

    def disconnect(self):
        """Mark session as disconnected."""
        self.status = "disconnected"
        self.left_at = timezone.now()
        self.total_time = self.duration
        self.save(update_fields=["status", "left_at", "total_time"])


class CollaborationActivity(models.Model):
    """
    Real-time collaboration activities within a room.
    Tracks all user actions for synchronization and history.
    """

    ACTIVITY_TYPES = [
        # Document editing
        ("text_insert", "Text Insert"),
        ("text_delete", "Text Delete"),
        ("text_format", "Text Format"),
        ("text_replace", "Text Replace"),
        # User presence
        ("user_join", "User Join"),
        ("user_leave", "User Leave"),
        ("cursor_move", "Cursor Move"),
        ("selection_change", "Selection Change"),
        # Collaboration
        ("comment_add", "Comment Add"),
        ("comment_reply", "Comment Reply"),
        ("comment_resolve", "Comment Resolve"),
        # System events
        ("document_save", "Document Save"),
        ("room_settings", "Room Settings Change"),
        ("permission_change", "Permission Change"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Activity identification
    room = models.ForeignKey(
        CollaborationRoom, on_delete=models.CASCADE, related_name="activities"
    )
    session = models.ForeignKey(
        CollaborationSession, on_delete=models.CASCADE, related_name="activities"
    )
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="collaboration_activities"
    )

    # Activity details
    activity_type = models.CharField(max_length=30, choices=ACTIVITY_TYPES)
    activity_data = models.JSONField(help_text="Activity-specific data")

    # Operational Transform data
    operation = models.JSONField(null=True, blank=True, help_text="OT operation data")
    operation_id = models.CharField(
        max_length=64, blank=True, help_text="Unique operation ID"
    )
    parent_operation_id = models.CharField(
        max_length=64, blank=True, help_text="Parent operation ID"
    )

    # Context
    document_version = models.PositiveIntegerField(
        help_text="Document version at time of activity"
    )
    position = models.JSONField(null=True, blank=True, help_text="Position in document")

    # Metadata
    client_timestamp = models.DateTimeField(help_text="Timestamp from client")
    server_timestamp = models.DateTimeField(default=timezone.now)
    sequence_number = models.PositiveIntegerField(
        help_text="Sequence number for ordering"
    )

    # Status
    is_applied = models.BooleanField(
        default=False, help_text="Whether operation has been applied"
    )
    is_broadcast = models.BooleanField(
        default=False, help_text="Whether activity has been broadcast"
    )

    class Meta:
        db_table = "collaboration_activities"
        ordering = ["sequence_number", "server_timestamp"]
        indexes = [
            models.Index(
                fields=["room", "sequence_number"], name="idx_activity_room_seq"
            ),
            models.Index(fields=["session"], name="idx_activity_session"),
            models.Index(fields=["activity_type"], name="idx_activity_type"),
            models.Index(fields=["server_timestamp"], name="idx_activity_timestamp"),
            models.Index(fields=["operation_id"], name="idx_activity_operation"),
            models.Index(fields=["is_applied"], name="idx_activity_applied"),
        ]

    def __str__(self):
        return f"{self.activity_type} by {self.user.username} in {self.room.name}"

    def save(self, *args, **kwargs):
        """Override save to set sequence number and operation ID."""
        if not self.sequence_number:
            # Get next sequence number for this room
            last_activity = (
                CollaborationActivity.objects.filter(room=self.room)
                .order_by("-sequence_number")
                .first()
            )
            self.sequence_number = (
                (last_activity.sequence_number + 1) if last_activity else 1
            )

        if not self.operation_id and self.operation:
            import secrets

            self.operation_id = secrets.token_urlsafe(16)

        super().save(*args, **kwargs)


class CursorPosition(models.Model):
    """
    Real-time cursor position tracking for collaboration.
    Stores current cursor/selection position for each user in a room.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Position tracking
    session = models.OneToOneField(
        CollaborationSession, on_delete=models.CASCADE, related_name="cursor_position"
    )
    room = models.ForeignKey(
        CollaborationRoom, on_delete=models.CASCADE, related_name="cursor_positions"
    )
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="cursor_positions"
    )

    # Cursor data
    position = models.JSONField(help_text="Cursor position data")
    selection = models.JSONField(null=True, blank=True, help_text="Text selection data")

    # Visual customization
    cursor_color = models.CharField(
        max_length=7, default="#007bff", help_text="Cursor color hex code"
    )
    user_label = models.CharField(
        max_length=100, blank=True, help_text="Display label for user"
    )

    # Metadata
    last_updated = models.DateTimeField(auto_now=True)
    is_visible = models.BooleanField(
        default=True, help_text="Whether cursor should be shown to others"
    )

    class Meta:
        db_table = "cursor_positions"
        unique_together = ["room", "user"]
        indexes = [
            models.Index(fields=["room"], name="idx_cursor_room"),
            models.Index(fields=["session"], name="idx_cursor_session"),
            models.Index(fields=["last_updated"], name="idx_cursor_updated"),
        ]

    def __str__(self):
        return f"{self.user.username} cursor in {self.room.name}"

    def save(self, *args, **kwargs):
        """Override save to set user label."""
        if not self.user_label:
            self.user_label = (
                f"{self.user.first_name} {self.user.last_name}".strip()
                or self.user.username
            )
        super().save(*args, **kwargs)
