"""
Serializers for documents app.
"""

from django.contrib.auth.models import User
from django.db import transaction
from rest_framework import serializers

from apps.organizations.models import Team

from .models import (
    Document,
    DocumentComment,
    DocumentMedia,
    DocumentPermission,
    DocumentVersion,
)


class UserBasicSerializer(serializers.ModelSerializer):
    """Basic user information for document contexts."""

    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "email"]
        read_only_fields = ["id", "username", "first_name", "last_name", "email"]


class DocumentMediaSerializer(serializers.ModelSerializer):
    """Serializer for document media attachments."""

    uploaded_by = UserBasicSerializer(read_only=True)
    file_url = serializers.ReadOnlyField()
    is_image = serializers.ReadOnlyField()
    is_video = serializers.ReadOnlyField()

    class Meta:
        model = DocumentMedia
        fields = [
            "id",
            "filename",
            "original_filename",
            "file_size",
            "mime_type",
            "media_type",
            "usage_type",
            "position_data",
            "width",
            "height",
            "duration",
            "alt_text",
            "caption",
            "file_url",
            "is_image",
            "is_video",
            "is_processed",
            "uploaded_by",
            "uploaded_at",
        ]
        read_only_fields = [
            "id",
            "file_size",
            "mime_type",
            "media_type",
            "width",
            "height",
            "duration",
            "file_url",
            "is_image",
            "is_video",
            "is_processed",
            "uploaded_by",
            "uploaded_at",
        ]


class DocumentMediaCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating document media attachments."""

    class Meta:
        model = DocumentMedia
        fields = [
            "file",
            "usage_type",
            "alt_text",
            "caption",
            "position_data",
        ]

    def create(self, validated_data):
        """Create media attachment with metadata extraction."""
        import os

        file_obj = validated_data["file"]
        validated_data["document"] = self.context["document"]
        validated_data["uploaded_by"] = self.context["request"].user
        validated_data["original_filename"] = file_obj.name
        validated_data["filename"] = os.path.splitext(file_obj.name)[0]
        validated_data["file_size"] = file_obj.size

        # Basic MIME type detection
        if hasattr(file_obj, "content_type") and file_obj.content_type:
            validated_data["mime_type"] = file_obj.content_type

            # Determine media type from MIME type
            if file_obj.content_type.startswith("image/"):
                validated_data["media_type"] = "image"
            elif file_obj.content_type.startswith("video/"):
                validated_data["media_type"] = "video"
            elif file_obj.content_type.startswith("audio/"):
                validated_data["media_type"] = "audio"
            elif file_obj.content_type == "application/pdf":
                validated_data["media_type"] = "pdf"
            else:
                validated_data["media_type"] = "other"
        else:
            validated_data["mime_type"] = "application/octet-stream"
            validated_data["media_type"] = "other"

        return super().create(validated_data)


class DocumentVersionSerializer(serializers.ModelSerializer):
    """Serializer for document versions."""

    created_by = UserBasicSerializer(read_only=True)

    class Meta:
        model = DocumentVersion
        fields = [
            "id",
            "version_number",
            "title",
            "content",
            "content_text",
            "change_summary",
            "word_count",
            "character_count",
            "created_by",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "version_number",
            "content_text",
            "word_count",
            "character_count",
            "created_by",
            "created_at",
        ]


class DocumentVersionCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating document versions."""

    class Meta:
        model = DocumentVersion
        fields = ["change_summary"]

    def create(self, validated_data):
        """Create a new version from current document state."""
        document = self.context["document"]
        user = self.context["request"].user

        return document.create_version(
            user=user, change_summary=validated_data.get("change_summary", "")
        )


class DocumentPermissionSerializer(serializers.ModelSerializer):
    """Serializer for document permissions."""

    user = UserBasicSerializer(read_only=True)
    user_id = serializers.UUIDField(write_only=True)
    granted_by = UserBasicSerializer(read_only=True)

    class Meta:
        model = DocumentPermission
        fields = [
            "id",
            "user",
            "user_id",
            "permission_level",
            "granted_by",
            "granted_at",
            "notes",
        ]
        read_only_fields = ["id", "user", "granted_by", "granted_at"]

    def validate_user_id(self, value):
        """Validate that user exists and is a team member."""
        try:
            user = User.objects.get(id=value)
        except User.DoesNotExist:
            raise serializers.ValidationError("User does not exist")

        document = self.context.get("document")
        if (
            document
            and not document.team.memberships.filter(
                user=user, status="active"
            ).exists()
        ):
            raise serializers.ValidationError(
                "User must be a team member to receive permissions"
            )

        return value

    def create(self, validated_data):
        """Create document permission."""
        user_id = validated_data.pop("user_id")
        user = User.objects.get(id=user_id)

        return DocumentPermission.objects.create(
            user=user,
            granted_by=self.context["request"].user,
            document=self.context["document"],
            **validated_data,
        )


class DocumentCommentSerializer(serializers.ModelSerializer):
    """Serializer for document comments."""

    user = UserBasicSerializer(read_only=True)
    resolved_by = UserBasicSerializer(read_only=True)
    reply_count = serializers.IntegerField(read_only=True)
    replies = serializers.SerializerMethodField()

    class Meta:
        model = DocumentComment
        fields = [
            "id",
            "content",
            "position_start",
            "position_end",
            "parent_comment",
            "user",
            "is_resolved",
            "resolved_by",
            "resolved_at",
            "reply_count",
            "replies",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "user",
            "is_resolved",
            "resolved_by",
            "resolved_at",
            "reply_count",
            "replies",
            "created_at",
            "updated_at",
        ]

    def get_replies(self, obj):
        """Get replies to this comment."""
        if obj.parent_comment is None:  # Only show replies for top-level comments
            replies = obj.replies.all()
            return DocumentCommentSerializer(
                replies, many=True, context=self.context
            ).data
        return []

    def create(self, validated_data):
        """Create document comment."""
        return DocumentComment.objects.create(
            user=self.context["request"].user,
            document=self.context["document"],
            **validated_data,
        )


class DocumentListSerializer(serializers.ModelSerializer):
    """Serializer for document list view."""

    created_by = UserBasicSerializer(read_only=True)
    updated_by = UserBasicSerializer(read_only=True)
    team_name = serializers.CharField(source="team.name", read_only=True)
    current_version = serializers.IntegerField(read_only=True)
    comment_count = serializers.SerializerMethodField()
    user_permission = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = [
            "id",
            "title",
            "document_type",
            "status",
            "is_public",
            "word_count",
            "character_count",
            "media_count",
            "tags",
            "team_name",
            "created_by",
            "updated_by",
            "current_version",
            "comment_count",
            "user_permission",
            "created_at",
            "updated_at",
        ]

    def get_comment_count(self, obj):
        """Get total comment count."""
        return obj.comments.count()

    def get_user_permission(self, obj):
        """Get current user's permission level."""
        user = self.context["request"].user
        return obj.get_user_permission(user)


class DocumentDetailSerializer(serializers.ModelSerializer):
    """Serializer for document detail view with rich content support."""

    created_by = UserBasicSerializer(read_only=True)
    updated_by = UserBasicSerializer(read_only=True)
    team_name = serializers.CharField(source="team.name", read_only=True)
    current_version = serializers.IntegerField(read_only=True)
    latest_version = DocumentVersionSerializer(read_only=True)
    user_permission = serializers.SerializerMethodField()
    permissions_count = serializers.SerializerMethodField()
    comment_count = serializers.SerializerMethodField()
    media_attachments = DocumentMediaSerializer(many=True, read_only=True)
    media_count = serializers.IntegerField(read_only=True)
    latest_content = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = [
            "id",
            "title",
            "content",
            "content_text",
            "draft_content",
            "latest_content",
            "has_unsaved_changes",
            "last_auto_save",
            "document_type",
            "status",
            "is_public",
            "word_count",
            "character_count",
            "media_count",
            "editor_settings",
            "tags",
            "metadata",
            "team_name",
            "created_by",
            "updated_by",
            "current_version",
            "latest_version",
            "user_permission",
            "permissions_count",
            "comment_count",
            "media_attachments",
            "created_at",
            "updated_at",
        ]

    def get_user_permission(self, obj):
        """Get current user's permission level."""
        user = self.context["request"].user
        return obj.get_user_permission(user)

    def get_latest_content(self, obj):
        """Get the most recent content (draft or published)."""
        return obj.get_latest_content()

    def get_permissions_count(self, obj):
        """Get total permissions count."""
        return obj.permissions.count()

    def get_comment_count(self, obj):
        """Get total comment count."""
        return obj.comments.count()


class DocumentAutoSaveSerializer(serializers.Serializer):
    """Serializer for auto-saving document content."""

    content = serializers.JSONField(help_text="Rich content to auto-save as draft")

    def validate_content(self, value):
        """Validate the content structure."""
        if not isinstance(value, dict):
            raise serializers.ValidationError("Content must be a valid JSON object")

        # Basic validation for common rich text formats
        if "type" in value and value["type"] not in ["doc", "paragraph", "text"]:
            # Allow any type for flexibility, but warn about unknown types
            pass

        return value


class DocumentPublishDraftSerializer(serializers.Serializer):
    """Serializer for publishing draft content."""

    create_version = serializers.BooleanField(
        default=True, help_text="Whether to create a new version when publishing"
    )
    version_summary = serializers.CharField(
        max_length=500,
        required=False,
        allow_blank=True,
        help_text="Summary of changes for the new version",
    )


class DocumentCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating documents."""

    team_id = serializers.UUIDField(write_only=True)

    class Meta:
        model = Document
        fields = [
            "title",
            "content",
            "document_type",
            "status",
            "is_public",
            "tags",
            "metadata",
            "team_id",
        ]

    def validate_team_id(self, value):
        """Validate that team exists and user has access."""
        try:
            team = Team.objects.get(id=value)
        except Team.DoesNotExist:
            raise serializers.ValidationError("Team does not exist")

        user = self.context["request"].user
        if not team.memberships.filter(user=user, status="active").exists():
            raise serializers.ValidationError("You are not a member of this team")

        return value

    def create(self, validated_data):
        """Create document with proper associations."""
        team_id = validated_data.pop("team_id")
        team = Team.objects.get(id=team_id)
        user = self.context["request"].user

        with transaction.atomic():
            # Create document
            document = Document.objects.create(
                team=team,
                created_by=user,
                updated_by=user,
                **validated_data,
            )

            # Create initial version
            document.create_version(user=user, change_summary="Initial version")

            # Grant admin permission to creator
            DocumentPermission.objects.create(
                document=document,
                user=user,
                permission_level="admin",
                granted_by=user,
                notes="Document creator",
            )

        return document


class DocumentUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating documents."""

    create_version = serializers.BooleanField(write_only=True, default=False)
    change_summary = serializers.CharField(
        write_only=True, required=False, allow_blank=True
    )

    class Meta:
        model = Document
        fields = [
            "title",
            "content",
            "document_type",
            "status",
            "is_public",
            "tags",
            "metadata",
            "create_version",
            "change_summary",
        ]

    def update(self, instance, validated_data):
        """Update document and optionally create version."""
        create_version = validated_data.pop("create_version", False)
        change_summary = validated_data.pop("change_summary", "")
        user = self.context["request"].user

        with transaction.atomic():
            # Update document
            instance.updated_by = user
            for attr, value in validated_data.items():
                setattr(instance, attr, value)
            instance.save()

            # Create version if requested
            if create_version:
                instance.create_version(user=user, change_summary=change_summary)

        return instance


class DocumentStatsSerializer(serializers.Serializer):
    """Serializer for document statistics."""

    total_documents = serializers.IntegerField()
    draft_documents = serializers.IntegerField()
    published_documents = serializers.IntegerField()
    archived_documents = serializers.IntegerField()
    total_words = serializers.IntegerField()
    total_comments = serializers.IntegerField()
    recent_activity_count = serializers.IntegerField()
    top_contributors = serializers.ListField()
