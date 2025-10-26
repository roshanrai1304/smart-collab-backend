"""
Serializers for collaboration app.
"""

from django.contrib.auth.models import User
from django.db import transaction
from rest_framework import serializers

from apps.documents.models import Document

from .models import (
    CollaborationActivity,
    CollaborationRoom,
    CollaborationSession,
    CursorPosition,
)


class UserBasicSerializer(serializers.ModelSerializer):
    """Basic user information for collaboration contexts."""

    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "email"]
        read_only_fields = ["id", "username", "first_name", "last_name", "email"]


class CollaborationRoomListSerializer(serializers.ModelSerializer):
    """Serializer for collaboration room list view."""

    created_by = UserBasicSerializer(read_only=True)
    document_title = serializers.CharField(source="document.title", read_only=True)
    team_name = serializers.CharField(source="team.name", read_only=True)
    active_participants_count = serializers.IntegerField(read_only=True)
    user_can_join = serializers.SerializerMethodField()

    class Meta:
        model = CollaborationRoom
        fields = [
            "id",
            "name",
            "description",
            "room_type",
            "status",
            "document_title",
            "team_name",
            "is_public",
            "max_participants",
            "active_participants_count",
            "enable_voice",
            "enable_video",
            "enable_cursor_tracking",
            "created_by",
            "user_can_join",
            "created_at",
            "last_activity",
        ]

    def get_user_can_join(self, obj):
        """Check if current user can join this room."""
        user = self.context["request"].user
        return obj.can_join(user)


class CollaborationRoomDetailSerializer(serializers.ModelSerializer):
    """Serializer for collaboration room detail view."""

    created_by = UserBasicSerializer(read_only=True)
    document_title = serializers.CharField(source="document.title", read_only=True)
    team_name = serializers.CharField(source="team.name", read_only=True)
    active_participants_count = serializers.IntegerField(read_only=True)
    is_full = serializers.BooleanField(read_only=True)
    user_can_join = serializers.SerializerMethodField()
    active_sessions = serializers.SerializerMethodField()

    class Meta:
        model = CollaborationRoom
        fields = [
            "id",
            "name",
            "description",
            "room_type",
            "status",
            "document_title",
            "team_name",
            "is_public",
            "max_participants",
            "active_participants_count",
            "is_full",
            "allow_anonymous",
            "enable_voice",
            "enable_video",
            "enable_screen_share",
            "enable_cursor_tracking",
            "settings",
            "metadata",
            "created_by",
            "user_can_join",
            "active_sessions",
            "created_at",
            "updated_at",
            "last_activity",
        ]

    def get_user_can_join(self, obj):
        """Check if current user can join this room."""
        user = self.context["request"].user
        return obj.can_join(user)

    def get_active_sessions(self, obj):
        """Get active sessions in this room."""
        active_sessions = obj.get_active_sessions()
        return CollaborationSessionSerializer(active_sessions, many=True).data


class CollaborationRoomCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating collaboration rooms."""

    document_id = serializers.UUIDField(write_only=True)

    class Meta:
        model = CollaborationRoom
        fields = [
            "name",
            "description",
            "room_type",
            "document_id",
            "is_public",
            "max_participants",
            "allow_anonymous",
            "enable_voice",
            "enable_video",
            "enable_screen_share",
            "enable_cursor_tracking",
            "settings",
            "metadata",
        ]

    def validate_document_id(self, value):
        """Validate that document exists and user has access."""
        try:
            document = Document.objects.get(id=value)
        except Document.DoesNotExist:
            raise serializers.ValidationError("Document does not exist")

        user = self.context["request"].user
        if not document.can_write(user):
            raise serializers.ValidationError(
                "You don't have permission to create rooms for this document"
            )

        return value

    def create(self, validated_data):
        """Create collaboration room."""
        document_id = validated_data.pop("document_id")
        document = Document.objects.get(id=document_id)
        user = self.context["request"].user

        with transaction.atomic():
            room = CollaborationRoom.objects.create(
                document=document,
                team=document.team,
                created_by=user,
                **validated_data,
            )

        return room


class CollaborationRoomUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating collaboration rooms."""

    class Meta:
        model = CollaborationRoom
        fields = [
            "name",
            "description",
            "status",
            "is_public",
            "max_participants",
            "allow_anonymous",
            "enable_voice",
            "enable_video",
            "enable_screen_share",
            "enable_cursor_tracking",
            "settings",
            "metadata",
        ]

    def update(self, instance, validated_data):
        """Update collaboration room."""
        user = self.context["request"].user

        # Check if user can modify this room
        if instance.created_by != user and not instance.document.can_admin(user):
            raise serializers.ValidationError(
                "You don't have permission to modify this room"
            )

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.save()
        return instance


class CollaborationSessionSerializer(serializers.ModelSerializer):
    """Serializer for collaboration sessions."""

    user = UserBasicSerializer(read_only=True)
    room_name = serializers.CharField(source="room.name", read_only=True)
    is_active = serializers.BooleanField(read_only=True)
    duration = serializers.DurationField(read_only=True)

    class Meta:
        model = CollaborationSession
        fields = [
            "id",
            "room_name",
            "user",
            "session_token",
            "status",
            "user_role",
            "is_active",
            "joined_at",
            "last_seen",
            "last_activity",
            "left_at",
            "duration",
            "total_time",
            "activity_count",
        ]
        read_only_fields = [
            "id",
            "session_token",
            "joined_at",
            "last_seen",
            "last_activity",
            "left_at",
            "total_time",
            "activity_count",
        ]


class CollaborationActivitySerializer(serializers.ModelSerializer):
    """Serializer for collaboration activities."""

    user = UserBasicSerializer(read_only=True)
    room_name = serializers.CharField(source="room.name", read_only=True)

    class Meta:
        model = CollaborationActivity
        fields = [
            "id",
            "room_name",
            "user",
            "activity_type",
            "activity_data",
            "operation",
            "operation_id",
            "parent_operation_id",
            "document_version",
            "position",
            "client_timestamp",
            "server_timestamp",
            "sequence_number",
            "is_applied",
            "is_broadcast",
        ]
        read_only_fields = [
            "id",
            "operation_id",
            "server_timestamp",
            "sequence_number",
            "is_applied",
            "is_broadcast",
        ]


class CursorPositionSerializer(serializers.ModelSerializer):
    """Serializer for cursor positions."""

    user = UserBasicSerializer(read_only=True)
    room_name = serializers.CharField(source="room.name", read_only=True)

    class Meta:
        model = CursorPosition
        fields = [
            "id",
            "room_name",
            "user",
            "position",
            "selection",
            "cursor_color",
            "user_label",
            "last_updated",
            "is_visible",
        ]
        read_only_fields = ["id", "user", "last_updated"]


class CollaborationStatsSerializer(serializers.Serializer):
    """Serializer for collaboration statistics."""

    total_rooms = serializers.IntegerField()
    active_rooms = serializers.IntegerField()
    total_sessions = serializers.IntegerField()
    active_sessions = serializers.IntegerField()
    total_activities = serializers.IntegerField()
    recent_activities_count = serializers.IntegerField()
    rooms_by_type = serializers.DictField()
    top_collaborators = serializers.ListField()
    average_session_duration = serializers.DurationField()


class JoinRoomSerializer(serializers.Serializer):
    """Serializer for joining a collaboration room."""

    user_role = serializers.ChoiceField(
        choices=CollaborationSession.USER_ROLES, default="editor"
    )
    client_info = serializers.JSONField(required=False, default=dict)

    def validate(self, data):
        """Validate join room data."""
        room = self.context.get("room")
        user = self.context["request"].user

        if not room:
            raise serializers.ValidationError("Room not found")

        if not room.can_join(user):
            raise serializers.ValidationError("Cannot join this room")

        return data


class WebSocketTokenSerializer(serializers.Serializer):
    """Serializer for WebSocket authentication tokens."""

    room_id = serializers.UUIDField()

    def validate_room_id(self, value):
        """Validate that room exists and user has access."""
        try:
            room = CollaborationRoom.objects.get(id=value)
        except CollaborationRoom.DoesNotExist:
            raise serializers.ValidationError("Room does not exist")

        user = self.context["request"].user
        if not room.can_join(user):
            raise serializers.ValidationError("Cannot access this room")

        return value
