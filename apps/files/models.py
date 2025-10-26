"""
File management models for Smart Collaborative Backend.

This module defines the file upload and storage structure:
- FileUpload (core file entity)
- FilePermission (access control)
- FileVersion (version control for files)
- FileShare (sharing links)
"""

import os
import uuid

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.db import models
from django.utils import timezone

from apps.documents.models import Document
from apps.organizations.models import Team


def upload_to_path(instance, filename):
    """Generate upload path for files."""
    # Create path: files/team_id/year/month/filename
    return f"files/{instance.team.id}/{timezone.now().year}/{timezone.now().month}/{filename}"


class FileUpload(models.Model):
    """
    Core file entity for file uploads and management.
    Files belong to teams and can be attached to documents.
    """

    FILE_TYPES = [
        ("image", "Image"),
        ("document", "Document"),
        ("video", "Video"),
        ("audio", "Audio"),
        ("archive", "Archive"),
        ("other", "Other"),
    ]

    UPLOAD_STATUS = [
        ("uploading", "Uploading"),
        ("processing", "Processing"),
        ("completed", "Completed"),
        ("failed", "Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # File information
    original_name = models.CharField(max_length=255, help_text="Original filename")
    file_name = models.CharField(max_length=255, help_text="Stored filename")
    file = models.FileField(upload_to=upload_to_path, max_length=500)
    file_size = models.PositiveIntegerField(help_text="File size in bytes")
    mime_type = models.CharField(max_length=100)
    file_type = models.CharField(max_length=20, choices=FILE_TYPES, default="other")

    # File metadata
    description = models.TextField(blank=True, help_text="File description")
    tags = models.JSONField(default=list, blank=True, help_text="File tags")
    metadata = models.JSONField(
        default=dict, blank=True, help_text="Additional metadata"
    )

    # Associations
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="files")
    uploaded_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="uploaded_files"
    )
    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="attachments",
        help_text="Document this file is attached to",
    )

    # Image-specific metadata
    is_image = models.BooleanField(default=False)
    image_width = models.PositiveIntegerField(null=True, blank=True)
    image_height = models.PositiveIntegerField(null=True, blank=True)

    # Upload status and processing
    upload_status = models.CharField(
        max_length=20, choices=UPLOAD_STATUS, default="uploading"
    )
    processing_info = models.JSONField(
        default=dict, blank=True, help_text="Processing status info"
    )

    # Security and access
    is_public = models.BooleanField(
        default=False, help_text="Public files can be accessed by all team members"
    )
    virus_scan_status = models.CharField(
        max_length=20,
        choices=[
            ("pending", "Pending"),
            ("clean", "Clean"),
            ("infected", "Infected"),
            ("error", "Error"),
        ],
        default="pending",
    )

    # Timestamps
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "file_uploads"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["team", "file_type"], name="idx_file_team_type"),
            models.Index(fields=["uploaded_by"], name="idx_file_uploaded_by"),
            models.Index(fields=["document"], name="idx_file_document"),
            models.Index(fields=["created_at"], name="idx_file_created_at"),
            models.Index(fields=["mime_type"], name="idx_file_mime_type"),
            models.Index(fields=["upload_status"], name="idx_file_status"),
        ]

    def __str__(self):
        return f"{self.original_name} ({self.team.name})"

    def clean(self):
        """Validate file data."""
        if self.file_size > 100 * 1024 * 1024:  # 100MB limit
            raise ValidationError("File size cannot exceed 100MB")

        # Validate file type based on mime type
        if not self.mime_type:
            raise ValidationError("MIME type is required")

    def save(self, *args, **kwargs):
        """Override save to set file metadata."""
        if self.file:
            # Set file name if not set
            if not self.file_name:
                self.file_name = os.path.basename(self.file.name)

            # Set original name if not set
            if not self.original_name:
                self.original_name = self.file_name

            # Set file size if not set
            if not self.file_size:
                self.file_size = self.file.size

            # Determine file type from mime type
            if not self.file_type or self.file_type == "other":
                self.file_type = self._determine_file_type()

            # Set image metadata
            if self.file_type == "image":
                self.is_image = True
                self._extract_image_metadata()

        super().save(*args, **kwargs)

    def _determine_file_type(self):
        """Determine file type from MIME type."""
        if not self.mime_type:
            return "other"

        mime_type_lower = self.mime_type.lower()

        if mime_type_lower.startswith("image/"):
            return "image"
        elif mime_type_lower in [
            "application/pdf",
            "application/msword",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "text/plain",
            "text/markdown",
        ]:
            return "document"
        elif mime_type_lower.startswith("video/"):
            return "video"
        elif mime_type_lower.startswith("audio/"):
            return "audio"
        elif mime_type_lower in [
            "application/zip",
            "application/x-rar-compressed",
            "application/x-tar",
            "application/gzip",
        ]:
            return "archive"
        else:
            return "other"

    def _extract_image_metadata(self):
        """Extract image metadata if it's an image file."""
        if not self.is_image or not self.file:
            return

        try:
            from PIL import Image

            with Image.open(self.file.path) as img:
                self.image_width = img.width
                self.image_height = img.height
        except (ImportError, Exception):
            # If PIL is not available or image cannot be processed
            pass

    @property
    def file_url(self):
        """Get the file URL."""
        if self.file:
            return self.file.url
        return None

    @property
    def file_extension(self):
        """Get file extension."""
        return os.path.splitext(self.original_name)[1].lower()

    @property
    def is_safe(self):
        """Check if file is safe (virus scan passed)."""
        return self.virus_scan_status == "clean"

    @property
    def human_readable_size(self):
        """Get human readable file size."""
        size = self.file_size
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"

    def get_user_permission(self, user):
        """Get user's permission level for this file."""
        try:
            permission = self.permissions.get(user=user)
            return permission.permission_level
        except FilePermission.DoesNotExist:
            # Check if user has team-level access
            if user in self.team.memberships.filter(status="active").values_list(
                "user", flat=True
            ):
                if self.is_public:
                    return "read"
                elif user == self.uploaded_by:
                    return "admin"
            return None

    def can_read(self, user):
        """Check if user can read this file."""
        permission = self.get_user_permission(user)
        return permission in ["read", "write", "admin"]

    def can_write(self, user):
        """Check if user can write to this file."""
        permission = self.get_user_permission(user)
        return permission in ["write", "admin"] or user == self.uploaded_by

    def can_admin(self, user):
        """Check if user can administer this file."""
        permission = self.get_user_permission(user)
        return permission == "admin" or user == self.uploaded_by

    def delete_file_from_storage(self):
        """Delete the actual file from storage."""
        if self.file:
            try:
                default_storage.delete(self.file.name)
            except Exception:
                pass  # File might already be deleted


class FilePermission(models.Model):
    """
    User permissions for files.
    Controls who can read, write, or administer files.
    """

    PERMISSION_LEVELS = [
        ("read", "Read Only"),
        ("write", "Read & Write"),
        ("admin", "Admin"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    file = models.ForeignKey(
        FileUpload, on_delete=models.CASCADE, related_name="permissions"
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    permission_level = models.CharField(max_length=10, choices=PERMISSION_LEVELS)

    # Permission metadata
    granted_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="granted_file_permissions"
    )
    granted_at = models.DateTimeField(default=timezone.now)
    notes = models.TextField(blank=True, help_text="Notes about this permission grant")

    class Meta:
        db_table = "file_permissions"
        unique_together = ["file", "user"]
        indexes = [
            models.Index(fields=["file", "user"], name="idx_file_perm_file_user"),
            models.Index(fields=["user"], name="idx_file_perm_user"),
            models.Index(fields=["granted_by"], name="idx_file_perm_granted"),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.file.original_name} ({self.permission_level})"

    def clean(self):
        """Validate permission data."""
        # Ensure user is a team member
        if not self.file.team.memberships.filter(
            user=self.user, status="active"
        ).exists():
            raise ValidationError(
                "User must be a team member to receive file permissions"
            )


class FileShare(models.Model):
    """
    File sharing links for external access.
    Allows temporary or permanent sharing of files.
    """

    SHARE_TYPES = [
        ("view", "View Only"),
        ("download", "Download"),
        ("edit", "Edit"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    file = models.ForeignKey(
        FileUpload, on_delete=models.CASCADE, related_name="shares"
    )

    # Share configuration
    share_token = models.CharField(
        max_length=64, unique=True, help_text="Unique share token"
    )
    share_type = models.CharField(max_length=20, choices=SHARE_TYPES, default="view")
    password_protected = models.BooleanField(default=False)
    password_hash = models.CharField(max_length=128, blank=True)

    # Access control
    max_downloads = models.PositiveIntegerField(
        null=True, blank=True, help_text="Maximum number of downloads"
    )
    download_count = models.PositiveIntegerField(default=0)
    expires_at = models.DateTimeField(
        null=True, blank=True, help_text="Share expiration time"
    )

    # Metadata
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(default=timezone.now)
    last_accessed = models.DateTimeField(null=True, blank=True)
    access_count = models.PositiveIntegerField(default=0)

    # Access tracking
    access_log = models.JSONField(
        default=list, blank=True, help_text="Access log entries"
    )

    class Meta:
        db_table = "file_shares"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["share_token"], name="idx_file_share_token"),
            models.Index(fields=["file"], name="idx_file_share_file"),
            models.Index(fields=["expires_at"], name="idx_file_share_expires"),
            models.Index(fields=["created_by"], name="idx_file_share_created"),
        ]

    def __str__(self):
        return f"Share: {self.file.original_name} ({self.share_type})"

    def save(self, *args, **kwargs):
        """Override save to generate share token."""
        if not self.share_token:
            import secrets

            self.share_token = secrets.token_urlsafe(32)
        super().save(*args, **kwargs)

    @property
    def is_expired(self):
        """Check if share link is expired."""
        if self.expires_at:
            return timezone.now() > self.expires_at
        return False

    @property
    def is_download_limit_reached(self):
        """Check if download limit is reached."""
        if self.max_downloads:
            return self.download_count >= self.max_downloads
        return False

    @property
    def is_active(self):
        """Check if share link is active."""
        return not self.is_expired and not self.is_download_limit_reached

    def record_access(self, ip_address=None, user_agent=None):
        """Record access to this share."""
        self.access_count += 1
        self.last_accessed = timezone.now()

        # Add to access log
        access_entry = {
            "timestamp": timezone.now().isoformat(),
            "ip_address": ip_address,
            "user_agent": user_agent,
        }

        if not self.access_log:
            self.access_log = []

        self.access_log.append(access_entry)

        # Keep only last 100 entries
        if len(self.access_log) > 100:
            self.access_log = self.access_log[-100:]

        self.save(update_fields=["access_count", "last_accessed", "access_log"])

    def record_download(self):
        """Record a download."""
        self.download_count += 1
        self.save(update_fields=["download_count"])

    def check_password(self, password):
        """Check if provided password is correct."""
        if not self.password_protected:
            return True

        from django.contrib.auth.hashers import check_password

        return check_password(password, self.password_hash)

    def set_password(self, password):
        """Set password for protected share."""
        from django.contrib.auth.hashers import make_password

        self.password_hash = make_password(password)
        self.password_protected = True
