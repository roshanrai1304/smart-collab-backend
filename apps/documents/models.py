"""
Document models for Smart Collaborative Backend.

This module defines the document management structure:
- Documents (core content entities)
- Document versions (version control and history)
- Document permissions (user access control)
- Document comments (collaboration and feedback)
"""

import uuid

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.organizations.models import Team


def document_media_path(instance, filename):
    """Generate file path for document media attachments."""
    return f"documents/{instance.document.id}/media/{filename}"


class Document(models.Model):
    """
    Core document entity for collaborative editing with rich content support.
    Documents belong to teams and support rich text, media, and advanced formatting.
    """

    DOCUMENT_TYPES = [
        ("text", "Plain Text"),
        ("markdown", "Markdown"),
        ("rich_text", "Rich Text Editor"),
        ("wysiwyg", "WYSIWYG Editor"),
    ]

    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("published", "Published"),
        ("archived", "Archived"),
        ("template", "Template"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)

    # Rich content storage - JSON structure for editor content
    content = models.JSONField(
        default=dict,
        blank=True,
        help_text="Rich content stored as JSON (supports text, formatting, media, etc.)",
    )

    # Draft content for auto-save functionality
    draft_content = models.JSONField(
        default=dict,
        blank=True,
        help_text="Draft content for auto-save (not yet published)",
    )

    # Plain text version for search and compatibility
    content_text = models.TextField(
        blank=True, help_text="Plain text version of content for search and indexing"
    )

    # Auto-save metadata
    last_auto_save = models.DateTimeField(
        null=True, blank=True, help_text="Timestamp of last auto-save"
    )
    has_unsaved_changes = models.BooleanField(
        default=False, help_text="Whether there are unsaved changes in draft_content"
    )

    # Associations
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="documents")
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="created_documents"
    )
    updated_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="updated_documents"
    )

    # Document metadata
    document_type = models.CharField(
        max_length=50, choices=DOCUMENT_TYPES, default="text"
    )

    # Status and visibility
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")
    is_public = models.BooleanField(
        default=False, help_text="Public documents are visible to all team members"
    )

    # Content metadata and statistics
    word_count = models.PositiveIntegerField(default=0)
    character_count = models.PositiveIntegerField(default=0)
    media_count = models.PositiveIntegerField(
        default=0, help_text="Number of media attachments"
    )

    # Rich content settings
    editor_settings = models.JSONField(
        default=dict,
        blank=True,
        help_text="Editor-specific settings (theme, plugins, etc.)",
    )

    # Timestamps
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    # Metadata and tags
    tags = models.JSONField(
        default=list, blank=True, help_text="List of tags for categorization"
    )
    metadata = models.JSONField(
        default=dict, blank=True, help_text="Additional document metadata"
    )

    class Meta:
        db_table = "documents"
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["team", "status"], name="idx_doc_team_status"),
            models.Index(fields=["created_by"], name="idx_doc_created_by"),
            models.Index(fields=["updated_at"], name="idx_doc_updated_at"),
            models.Index(fields=["team", "is_public"], name="idx_doc_team_public"),
        ]

    def __str__(self):
        return f"{self.title} ({self.team.name})"

    def clean(self):
        """Validate document data."""
        if not self.title.strip():
            raise ValidationError("Document title cannot be empty")

    def save(self, *args, **kwargs):
        """Override save to update content statistics."""
        # Extract plain text from rich content for statistics
        if isinstance(self.content, dict):
            # Extract text from rich content structure
            self.content_text = self._extract_text_from_rich_content(self.content)
        elif isinstance(self.content, str):
            # Handle legacy plain text content
            self.content_text = self.content
        else:
            self.content_text = ""

        # Update content statistics based on plain text
        if self.content_text:
            self.word_count = len(self.content_text.split())
            self.character_count = len(self.content_text)
        else:
            self.word_count = 0
            self.character_count = 0

        # Update media count
        if self.pk:  # Only for existing documents
            self.media_count = self.media_attachments.count()

        super().save(*args, **kwargs)

    def _extract_text_from_rich_content(self, content):
        """Extract plain text from rich content JSON structure."""
        if not content:
            return ""

        text_parts = []

        # Handle different rich content formats
        if isinstance(content, dict):
            # Handle block-based editors (like Editor.js, Draft.js)
            if "blocks" in content:
                for block in content.get("blocks", []):
                    if isinstance(block, dict) and "data" in block:
                        block_data = block["data"]
                        if "text" in block_data:
                            text_parts.append(block_data["text"])
                        elif "caption" in block_data:
                            text_parts.append(block_data["caption"])

            # Handle document-based editors (like ProseMirror, Slate)
            elif "content" in content:
                text_parts.append(self._extract_from_prosemirror(content))

            # Handle simple text content
            elif "text" in content:
                text_parts.append(content["text"])

        return " ".join(text_parts).strip()

    def _extract_from_prosemirror(self, content):
        """Extract text from ProseMirror document structure."""
        text_parts = []

        def extract_text_recursive(node):
            if isinstance(node, dict):
                if node.get("type") == "text":
                    text_parts.append(node.get("text", ""))
                elif "content" in node:
                    for child in node["content"]:
                        extract_text_recursive(child)

        if "content" in content:
            for node in content["content"]:
                extract_text_recursive(node)

        return " ".join(text_parts)

    @property
    def current_version(self):
        """Get the current version number."""
        return self.versions.count()

    @property
    def latest_version(self):
        """Get the latest version object."""
        return self.versions.first()

    def create_version(self, user, change_summary=""):
        """Create a new version of the document."""
        version_number = self.current_version + 1
        return DocumentVersion.objects.create(
            document=self,
            version_number=version_number,
            title=self.title,
            content=self.content,
            change_summary=change_summary,
            created_by=user,
        )

    def get_user_permission(self, user):
        """Get user's permission level for this document."""
        try:
            permission = self.permissions.get(user=user)
            return permission.permission_level
        except DocumentPermission.DoesNotExist:
            # Check if user has team-level access
            if user in self.team.memberships.filter(status="active").values_list(
                "user", flat=True
            ):
                return "read" if self.is_public else None
            return None

    def can_read(self, user):
        """Check if user can read this document."""
        permission = self.get_user_permission(user)
        return permission in ["read", "write", "admin"]

    def can_write(self, user):
        """Check if user can write to this document."""
        permission = self.get_user_permission(user)
        return permission in ["write", "admin"]

    def can_admin(self, user):
        """Check if user can administer this document."""
        permission = self.get_user_permission(user)
        return permission == "admin" or user == self.created_by

    def auto_save_draft(self, content, user):
        """Save draft content without creating a new version."""
        from django.utils import timezone

        self.draft_content = content
        self.has_unsaved_changes = True
        self.last_auto_save = timezone.now()
        self.updated_by = user

        # Save only the auto-save fields
        self.save(
            update_fields=[
                "draft_content",
                "has_unsaved_changes",
                "last_auto_save",
                "updated_by",
            ]
        )

        return True

    def publish_draft(self, user):
        """Publish draft content as the main content and create a version."""
        if not self.has_unsaved_changes or not self.draft_content:
            return False

        # Move draft to main content
        self.content = self.draft_content
        self.updated_by = user
        self.has_unsaved_changes = False

        # This will trigger the normal save() method to update statistics
        self.save()

        # Clear draft after publishing
        self.draft_content = {}
        self.save(update_fields=["draft_content"])

        return True

    def get_latest_content(self):
        """Get the most recent content (draft if available, otherwise published)."""
        if self.has_unsaved_changes and self.draft_content:
            return self.draft_content
        return self.content

    def discard_draft(self):
        """Discard unsaved draft changes."""
        self.draft_content = {}
        self.has_unsaved_changes = False
        self.last_auto_save = None
        self.save(
            update_fields=["draft_content", "has_unsaved_changes", "last_auto_save"]
        )


class DocumentMedia(models.Model):
    """
    Media attachments for documents (images, videos, files, etc.).
    Supports inline embedding and file attachments.
    """

    MEDIA_TYPES = [
        ("image", "Image"),
        ("video", "Video"),
        ("audio", "Audio"),
        ("document", "Document"),
        ("spreadsheet", "Spreadsheet"),
        ("presentation", "Presentation"),
        ("pdf", "PDF"),
        ("archive", "Archive"),
        ("other", "Other"),
    ]

    USAGE_TYPES = [
        ("inline", "Inline Content"),
        ("attachment", "File Attachment"),
        ("background", "Background/Cover"),
        ("thumbnail", "Thumbnail"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(
        Document, on_delete=models.CASCADE, related_name="media_attachments"
    )

    # File information
    file = models.FileField(upload_to=document_media_path)
    filename = models.CharField(max_length=255)
    original_filename = models.CharField(max_length=255)
    file_size = models.PositiveIntegerField(help_text="File size in bytes")
    mime_type = models.CharField(max_length=100)

    # Media metadata
    media_type = models.CharField(max_length=20, choices=MEDIA_TYPES)
    usage_type = models.CharField(
        max_length=20, choices=USAGE_TYPES, default="attachment"
    )

    # Rich content positioning (for inline media)
    position_data = models.JSONField(
        default=dict, blank=True, help_text="Position and styling data for inline media"
    )

    # Image/Video specific metadata
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)
    duration = models.FloatField(
        null=True, blank=True, help_text="Duration in seconds for video/audio"
    )

    # Alt text and accessibility
    alt_text = models.CharField(
        max_length=255, blank=True, help_text="Alt text for accessibility"
    )
    caption = models.TextField(blank=True, help_text="Media caption")

    # Upload metadata
    uploaded_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="uploaded_media"
    )
    uploaded_at = models.DateTimeField(default=timezone.now)

    # Status and settings
    is_processed = models.BooleanField(
        default=False, help_text="Whether media processing is complete"
    )
    processing_data = models.JSONField(
        default=dict, blank=True, help_text="Processing status and metadata"
    )

    class Meta:
        db_table = "document_media"
        ordering = ["-uploaded_at"]
        indexes = [
            models.Index(fields=["document", "media_type"], name="idx_media_doc_type"),
            models.Index(fields=["document", "usage_type"], name="idx_media_doc_usage"),
            models.Index(fields=["uploaded_by"], name="idx_media_uploader"),
        ]

    def __str__(self):
        return f"{self.filename} ({self.document.title})"

    @property
    def file_url(self):
        """Get the URL for accessing the file."""
        if self.file:
            return self.file.url
        return None

    @property
    def is_image(self):
        """Check if this is an image file."""
        return self.media_type == "image"

    @property
    def is_video(self):
        """Check if this is a video file."""
        return self.media_type == "video"

    def get_thumbnail_url(self, size="medium"):
        """Get thumbnail URL (to be implemented with image processing)."""
        if self.is_image and self.is_processed:
            # This would integrate with image processing service
            return f"{self.file_url}?thumbnail={size}"
        return self.file_url


class DocumentVersion(models.Model):
    """
    Version control for documents.
    Tracks changes and maintains history.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(
        Document, on_delete=models.CASCADE, related_name="versions"
    )
    version_number = models.PositiveIntegerField()
    title = models.CharField(max_length=255)

    # Rich content version storage
    content = models.JSONField(
        default=dict, help_text="Rich content snapshot at this version"
    )
    content_text = models.TextField(
        blank=True, help_text="Plain text version for this snapshot"
    )
    change_summary = models.TextField(
        blank=True, help_text="Summary of changes in this version"
    )

    # Version metadata
    word_count = models.PositiveIntegerField(default=0)
    character_count = models.PositiveIntegerField(default=0)

    # Authorship
    created_by = models.ForeignKey(User, on_delete=models.PROTECT)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "document_versions"
        unique_together = ["document", "version_number"]
        ordering = ["-version_number"]
        indexes = [
            models.Index(fields=["document", "version_number"], name="idx_ver_doc_num"),
            models.Index(fields=["created_by"], name="idx_ver_created_by"),
            models.Index(fields=["created_at"], name="idx_ver_created_at"),
        ]

    def __str__(self):
        return f"{self.document.title} v{self.version_number}"

    def save(self, *args, **kwargs):
        """Override save to update content statistics."""
        # Extract plain text from rich content for statistics
        if isinstance(self.content, dict):
            # Use the same text extraction logic as Document
            self.content_text = self._extract_text_from_rich_content(self.content)
        elif isinstance(self.content, str):
            # Handle legacy plain text content
            self.content_text = self.content
        else:
            self.content_text = ""

        # Update content statistics based on plain text
        if self.content_text:
            self.word_count = len(self.content_text.split())
            self.character_count = len(self.content_text)
        else:
            self.word_count = 0
            self.character_count = 0

        super().save(*args, **kwargs)

    def _extract_text_from_rich_content(self, content):
        """Extract plain text from rich content JSON structure."""
        if not content:
            return ""

        text_parts = []

        # Handle different rich content formats
        if isinstance(content, dict):
            # Handle block-based editors (like Editor.js, Draft.js)
            if "blocks" in content:
                for block in content.get("blocks", []):
                    if isinstance(block, dict) and "data" in block:
                        block_data = block["data"]
                        if "text" in block_data:
                            text_parts.append(block_data["text"])
                        elif "caption" in block_data:
                            text_parts.append(block_data["caption"])

            # Handle document-based editors (like ProseMirror, Slate)
            elif "content" in content:
                text_parts.append(self._extract_from_prosemirror(content))

            # Handle simple text content
            elif "text" in content:
                text_parts.append(content["text"])

        return " ".join(text_parts).strip()

    def _extract_from_prosemirror(self, content):
        """Extract text from ProseMirror document structure."""
        text_parts = []

        def extract_text_recursive(node):
            if isinstance(node, dict):
                if node.get("type") == "text":
                    text_parts.append(node.get("text", ""))
                elif "content" in node:
                    for child in node["content"]:
                        extract_text_recursive(child)

        if "content" in content:
            for node in content["content"]:
                extract_text_recursive(node)

        return " ".join(text_parts)


class DocumentPermission(models.Model):
    """
    User permissions for documents.
    Controls who can read, write, or administer documents.
    """

    PERMISSION_LEVELS = [
        ("read", "Read Only"),
        ("write", "Read & Write"),
        ("admin", "Admin"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(
        Document, on_delete=models.CASCADE, related_name="permissions"
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    permission_level = models.CharField(max_length=10, choices=PERMISSION_LEVELS)

    # Permission metadata
    granted_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="granted_permissions"
    )
    granted_at = models.DateTimeField(default=timezone.now)
    notes = models.TextField(blank=True, help_text="Notes about this permission grant")

    class Meta:
        db_table = "document_permissions"
        unique_together = ["document", "user"]
        indexes = [
            models.Index(fields=["document", "user"], name="idx_perm_doc_user"),
            models.Index(fields=["user"], name="idx_perm_user"),
            models.Index(fields=["granted_by"], name="idx_perm_granted_by"),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.document.title} ({self.permission_level})"

    def clean(self):
        """Validate permission data."""
        # Ensure user is a team member
        if not self.document.team.memberships.filter(
            user=self.user, status="active"
        ).exists():
            raise ValidationError("User must be a team member to receive permissions")


class DocumentComment(models.Model):
    """
    Comments and annotations on documents.
    Supports threading and inline comments.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(
        Document, on_delete=models.CASCADE, related_name="comments"
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField()

    # Position in document (for inline comments)
    position_start = models.PositiveIntegerField(
        null=True, blank=True, help_text="Start position in document content"
    )
    position_end = models.PositiveIntegerField(
        null=True, blank=True, help_text="End position in document content"
    )

    # Threading support
    parent_comment = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="replies",
    )

    # Status
    is_resolved = models.BooleanField(
        default=False, help_text="Mark comment as resolved"
    )
    resolved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resolved_comments",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)

    # Timestamps
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "document_comments"
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["document", "created_at"], name="idx_comm_doc_time"),
            models.Index(fields=["user"], name="idx_comm_user"),
            models.Index(fields=["parent_comment"], name="idx_comm_parent"),
            models.Index(fields=["is_resolved"], name="idx_comm_resolved"),
        ]

    def __str__(self):
        return f"Comment on {self.document.title} by {self.user.username}"

    @property
    def is_reply(self):
        """Check if this comment is a reply to another comment."""
        return self.parent_comment is not None

    @property
    def reply_count(self):
        """Get the number of replies to this comment."""
        return self.replies.count()

    def resolve(self, user):
        """Mark comment as resolved."""
        self.is_resolved = True
        self.resolved_by = user
        self.resolved_at = timezone.now()
        self.save(update_fields=["is_resolved", "resolved_by", "resolved_at"])
