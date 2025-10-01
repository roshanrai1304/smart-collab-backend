"""
Serializers for files app.
"""

import mimetypes
import os

from django.contrib.auth.models import User
from django.db import transaction
from rest_framework import serializers

from apps.documents.models import Document
from apps.organizations.models import Team

from .models import FilePermission, FileShare, FileUpload


class UserBasicSerializer(serializers.ModelSerializer):
    """Basic user information for file contexts."""

    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "email"]
        read_only_fields = ["id", "username", "first_name", "last_name", "email"]


class FileUploadListSerializer(serializers.ModelSerializer):
    """Serializer for file list view."""

    uploaded_by = UserBasicSerializer(read_only=True)
    team_name = serializers.CharField(source="team.name", read_only=True)
    document_title = serializers.CharField(source="document.title", read_only=True)
    user_permission = serializers.SerializerMethodField()
    file_url = serializers.CharField(read_only=True)
    human_readable_size = serializers.CharField(read_only=True)
    file_extension = serializers.CharField(read_only=True)

    class Meta:
        model = FileUpload
        fields = [
            "id",
            "original_name",
            "file_name",
            "file_type",
            "file_size",
            "human_readable_size",
            "file_extension",
            "mime_type",
            "description",
            "tags",
            "is_image",
            "image_width",
            "image_height",
            "upload_status",
            "is_public",
            "virus_scan_status",
            "team_name",
            "document_title",
            "uploaded_by",
            "user_permission",
            "file_url",
            "created_at",
            "updated_at",
        ]

    def get_user_permission(self, obj):
        """Get current user's permission level."""
        user = self.context["request"].user
        return obj.get_user_permission(user)


class FileUploadDetailSerializer(serializers.ModelSerializer):
    """Serializer for file detail view."""

    uploaded_by = UserBasicSerializer(read_only=True)
    team_name = serializers.CharField(source="team.name", read_only=True)
    document_title = serializers.CharField(source="document.title", read_only=True)
    user_permission = serializers.SerializerMethodField()
    permissions_count = serializers.SerializerMethodField()
    shares_count = serializers.SerializerMethodField()
    file_url = serializers.CharField(read_only=True)
    human_readable_size = serializers.CharField(read_only=True)
    file_extension = serializers.CharField(read_only=True)
    is_safe = serializers.BooleanField(read_only=True)

    class Meta:
        model = FileUpload
        fields = [
            "id",
            "original_name",
            "file_name",
            "file_type",
            "file_size",
            "human_readable_size",
            "file_extension",
            "mime_type",
            "description",
            "tags",
            "metadata",
            "is_image",
            "image_width",
            "image_height",
            "upload_status",
            "processing_info",
            "is_public",
            "virus_scan_status",
            "is_safe",
            "team_name",
            "document_title",
            "uploaded_by",
            "user_permission",
            "permissions_count",
            "shares_count",
            "file_url",
            "created_at",
            "updated_at",
        ]

    def get_user_permission(self, obj):
        """Get current user's permission level."""
        user = self.context["request"].user
        return obj.get_user_permission(user)

    def get_permissions_count(self, obj):
        """Get total permissions count."""
        return obj.permissions.count()

    def get_shares_count(self, obj):
        """Get total shares count."""
        return obj.shares.count()


class FileUploadCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating file uploads."""

    file = serializers.FileField(write_only=True)
    team_id = serializers.UUIDField(write_only=True)
    document_id = serializers.UUIDField(
        write_only=True, required=False, allow_null=True
    )

    class Meta:
        model = FileUpload
        fields = [
            "file",
            "description",
            "tags",
            "metadata",
            "is_public",
            "team_id",
            "document_id",
        ]

    def validate_file(self, value):
        """Validate uploaded file."""
        if not value:
            raise serializers.ValidationError("File is required")

        # Check file size (100MB limit)
        if value.size > 100 * 1024 * 1024:
            raise serializers.ValidationError("File size cannot exceed 100MB")

        # Check for potentially dangerous file types
        dangerous_extensions = [
            ".exe",
            ".bat",
            ".cmd",
            ".com",
            ".pif",
            ".scr",
            ".vbs",
            ".js",
            ".jar",
            ".app",
            ".deb",
            ".pkg",
            ".dmg",
            ".sh",
            ".ps1",
            ".msi",
        ]

        file_extension = os.path.splitext(value.name)[1].lower()
        if file_extension in dangerous_extensions:
            raise serializers.ValidationError(
                f"File type {file_extension} is not allowed for security reasons"
            )

        return value

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

    def validate_document_id(self, value):
        """Validate document if provided."""
        if not value:
            return value

        try:
            document = Document.objects.get(id=value)
        except Document.DoesNotExist:
            raise serializers.ValidationError("Document does not exist")

        user = self.context["request"].user
        if not document.can_write(user):
            raise serializers.ValidationError(
                "You don't have permission to attach files to this document"
            )

        return value

    def create(self, validated_data):
        """Create file upload with proper associations."""
        file_data = validated_data.pop("file")
        team_id = validated_data.pop("team_id")
        document_id = validated_data.pop("document_id", None)

        team = Team.objects.get(id=team_id)
        document = Document.objects.get(id=document_id) if document_id else None
        user = self.context["request"].user

        # Determine MIME type
        mime_type, _ = mimetypes.guess_type(file_data.name)
        if not mime_type:
            mime_type = "application/octet-stream"

        with transaction.atomic():
            # Create file upload
            file_upload = FileUpload.objects.create(
                file=file_data,
                original_name=file_data.name,
                file_size=file_data.size,
                mime_type=mime_type,
                team=team,
                document=document,
                uploaded_by=user,
                upload_status="completed",
                virus_scan_status="clean",  # In production, integrate with virus scanner
                **validated_data,
            )

            # Grant admin permission to uploader
            FilePermission.objects.create(
                file=file_upload,
                user=user,
                permission_level="admin",
                granted_by=user,
                notes="File uploader",
            )

        return file_upload


class FileUploadUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating file uploads."""

    class Meta:
        model = FileUpload
        fields = [
            "description",
            "tags",
            "metadata",
            "is_public",
        ]

    def update(self, instance, validated_data):
        """Update file upload."""
        user = self.context["request"].user

        # Check if user can modify this file
        if not instance.can_write(user):
            raise serializers.ValidationError(
                "You don't have permission to modify this file"
            )

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.save()
        return instance


class FilePermissionSerializer(serializers.ModelSerializer):
    """Serializer for file permissions."""

    user = UserBasicSerializer(read_only=True)
    user_id = serializers.UUIDField(write_only=True)
    granted_by = UserBasicSerializer(read_only=True)

    class Meta:
        model = FilePermission
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

        file_obj = self.context.get("file")
        if (
            file_obj
            and not file_obj.team.memberships.filter(
                user=user, status="active"
            ).exists()
        ):
            raise serializers.ValidationError(
                "User must be a team member to receive file permissions"
            )

        return value

    def create(self, validated_data):
        """Create file permission."""
        user_id = validated_data.pop("user_id")
        user = User.objects.get(id=user_id)

        return FilePermission.objects.create(
            user=user,
            granted_by=self.context["request"].user,
            file=self.context["file"],
            **validated_data,
        )


class FileShareSerializer(serializers.ModelSerializer):
    """Serializer for file shares."""

    created_by = UserBasicSerializer(read_only=True)
    file_name = serializers.CharField(source="file.original_name", read_only=True)
    is_active = serializers.BooleanField(read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    is_download_limit_reached = serializers.BooleanField(read_only=True)
    share_url = serializers.SerializerMethodField()

    class Meta:
        model = FileShare
        fields = [
            "id",
            "share_token",
            "share_type",
            "password_protected",
            "max_downloads",
            "download_count",
            "expires_at",
            "access_count",
            "last_accessed",
            "file_name",
            "created_by",
            "created_at",
            "is_active",
            "is_expired",
            "is_download_limit_reached",
            "share_url",
        ]
        read_only_fields = [
            "id",
            "share_token",
            "download_count",
            "access_count",
            "last_accessed",
            "created_by",
            "created_at",
        ]

    def get_share_url(self, obj):
        """Get the full share URL."""
        request = self.context.get("request")
        if request:
            return request.build_absolute_uri(f"/api/v1/files/share/{obj.share_token}/")
        return f"/api/v1/files/share/{obj.share_token}/"


class FileShareCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating file shares."""

    password = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = FileShare
        fields = [
            "share_type",
            "password_protected",
            "password",
            "max_downloads",
            "expires_at",
        ]

    def validate(self, data):
        """Validate share data."""
        if data.get("password_protected") and not data.get("password"):
            raise serializers.ValidationError(
                "Password is required for password-protected shares"
            )

        return data

    def create(self, validated_data):
        """Create file share."""
        password = validated_data.pop("password", None)

        share = FileShare.objects.create(
            file=self.context["file"],
            created_by=self.context["request"].user,
            **validated_data,
        )

        if password:
            share.set_password(password)
            share.save()

        return share


class FileStatsSerializer(serializers.Serializer):
    """Serializer for file statistics."""

    total_files = serializers.IntegerField()
    total_size = serializers.IntegerField()
    total_size_readable = serializers.CharField()
    files_by_type = serializers.DictField()
    recent_uploads_count = serializers.IntegerField()
    top_uploaders = serializers.ListField()
    storage_usage_by_team = serializers.ListField()


class FileAttachToDocumentSerializer(serializers.Serializer):
    """Serializer for attaching files to documents."""

    document_id = serializers.UUIDField()

    def validate_document_id(self, value):
        """Validate document exists and user has write access."""
        try:
            document = Document.objects.get(id=value)
        except Document.DoesNotExist:
            raise serializers.ValidationError("Document does not exist")

        user = self.context["request"].user
        if not document.can_write(user):
            raise serializers.ValidationError(
                "You don't have permission to attach files to this document"
            )

        # Check if document is in the same team as the file
        file_obj = self.context.get("file")
        if file_obj and document.team != file_obj.team:
            raise serializers.ValidationError(
                "Document and file must be in the same team"
            )

        return value
