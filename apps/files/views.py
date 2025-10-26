"""
API views for files app.
"""

import os
from datetime import timedelta

from django.db.models import Q, Sum
from django.http import FileResponse, Http404
from django.utils import timezone
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import generics
from rest_framework import permissions as drf_permissions
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from apps.organizations.models import Team

from .models import FileShare, FileUpload
from .permissions import (
    CanManageFilePermissions,
    FilePermissionMixin,
    IsFileReader,
    IsVirusScanClean,
)
from .serializers import (
    FilePermissionSerializer,
    FileStatsSerializer,
    FileUploadCreateSerializer,
    FileUploadDetailSerializer,
    FileUploadListSerializer,
    FileUploadUpdateSerializer,
)


@extend_schema_view(
    list=extend_schema(
        summary="List files",
        description="Get all files accessible to the user within their teams",
    ),
    create=extend_schema(
        summary="Upload file",
        description="Upload a new file to a team",
    ),
    retrieve=extend_schema(
        summary="Get file details",
        description="Get detailed information about a file",
    ),
    update=extend_schema(
        summary="Update file",
        description="Update file metadata and properties",
    ),
    destroy=extend_schema(
        summary="Delete file",
        description="Delete a file (admin only)",
    ),
)
class FileUploadViewSet(FilePermissionMixin, ModelViewSet):
    """ViewSet for file upload and management operations."""

    lookup_field = "id"
    parser_classes = [MultiPartParser]

    def get_queryset(self):
        """Get files accessible to the user."""
        user = self.request.user
        if not user.is_authenticated:
            return FileUpload.objects.none()

        # Get user's teams
        user_teams = Team.objects.filter(
            memberships__user=user, memberships__status="active"
        )

        # Get files from user's teams
        queryset = FileUpload.objects.filter(team__in=user_teams)

        # Apply filters
        queryset = self._apply_filters(queryset)

        return queryset.select_related(
            "team", "uploaded_by", "document"
        ).prefetch_related("permissions", "shares")

    def _apply_filters(self, queryset):
        """Apply various filters based on query parameters."""
        # Filter by team
        team_id = self.request.query_params.get("team")
        if team_id:
            queryset = queryset.filter(team_id=team_id)

        # Filter by file type
        file_type = self.request.query_params.get("type")
        if file_type:
            queryset = queryset.filter(file_type=file_type)

        # Filter by document
        document_id = self.request.query_params.get("document")
        if document_id:
            queryset = queryset.filter(document_id=document_id)

        # Search by filename
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(
                Q(original_name__icontains=search) | Q(description__icontains=search)
            )

        # Filter by tags
        tags = self.request.query_params.get("tags")
        if tags:
            tag_list = [tag.strip() for tag in tags.split(",")]
            queryset = queryset.filter(tags__overlap=tag_list)

        # Filter by upload status
        upload_status = self.request.query_params.get("status")
        if upload_status:
            queryset = queryset.filter(upload_status=upload_status)

        return queryset

    def get_serializer_class(self):
        """Return appropriate serializer class."""
        if self.action == "list":
            return FileUploadListSerializer
        elif self.action == "create":
            return FileUploadCreateSerializer
        elif self.action in ["update", "partial_update"]:
            return FileUploadUpdateSerializer
        else:
            return FileUploadDetailSerializer

    def create(self, request, *args, **kwargs):
        """Upload a file and return detailed response."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        file_upload = serializer.save()

        # Return detailed file information
        detail_serializer = FileUploadDetailSerializer(
            file_upload, context={"request": request}
        )
        headers = self.get_success_headers(detail_serializer.data)
        return Response(
            detail_serializer.data, status=status.HTTP_201_CREATED, headers=headers
        )

    @action(
        detail=True,
        methods=["get"],
        permission_classes=[IsFileReader, IsVirusScanClean],
    )
    def download(self, request, id=None):
        """Download file."""
        file_upload = self.get_object()

        if not file_upload.file:
            raise Http404("File not found")

        # Check if file exists
        if not os.path.exists(file_upload.file.path):
            raise Http404("File not found on storage")

        # Create file response
        response = FileResponse(
            open(file_upload.file.path, "rb"),
            content_type=file_upload.mime_type,
            as_attachment=True,
            filename=file_upload.original_name,
        )

        response["Content-Length"] = file_upload.file_size
        return response

    @action(
        detail=True,
        methods=["get", "post"],
        permission_classes=[CanManageFilePermissions],
    )
    def permissions(self, request, id=None):
        """Manage file permissions."""
        file_upload = self.get_object()

        if request.method == "GET":
            permissions_qs = file_upload.permissions.all().select_related(
                "user", "granted_by"
            )
            serializer = FilePermissionSerializer(permissions_qs, many=True)
            return Response(serializer.data)

        elif request.method == "POST":
            serializer = FilePermissionSerializer(
                data=request.data, context={"request": request, "file": file_upload}
            )
            if serializer.is_valid():
                permission = serializer.save()
                return Response(
                    FilePermissionSerializer(permission).data,
                    status=status.HTTP_201_CREATED,
                )
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(
        detail=False,
        methods=["get"],
        permission_classes=[drf_permissions.IsAuthenticated],
    )
    def stats(self, request):
        """Get file statistics for user's teams."""
        user = request.user
        user_teams = Team.objects.filter(
            memberships__user=user, memberships__status="active"
        )

        # Base queryset
        files = FileUpload.objects.filter(team__in=user_teams)

        # Calculate statistics
        total_size = files.aggregate(Sum("file_size"))["file_size__sum"] or 0

        def human_readable_size(size):
            for unit in ["B", "KB", "MB", "GB", "TB"]:
                if size < 1024:
                    return f"{size:.1f} {unit}"
                size /= 1024
            return f"{size:.1f} PB"

        # Files by type
        files_by_type = {}
        for file_type, _ in FileUpload.FILE_TYPES:
            count = files.filter(file_type=file_type).count()
            if count > 0:
                files_by_type[file_type] = count

        stats = {
            "total_files": files.count(),
            "total_size": total_size,
            "total_size_readable": human_readable_size(total_size),
            "files_by_type": files_by_type,
            "recent_uploads_count": files.filter(
                created_at__gte=timezone.now() - timedelta(days=7)
            ).count(),
        }

        serializer = FileStatsSerializer(stats)
        return Response(serializer.data)


class FileShareAccessView(generics.RetrieveAPIView):
    """Public view for accessing shared files."""

    permission_classes = [drf_permissions.AllowAny]
    lookup_field = "share_token"

    def get_queryset(self):
        """Get active file shares."""
        return FileShare.objects.filter(expires_at__gt=timezone.now()).select_related(
            "file"
        )

    def get_object(self):
        """Get file share by token."""
        share_token = self.kwargs["share_token"]
        try:
            share = FileShare.objects.get(share_token=share_token)
        except FileShare.DoesNotExist:
            raise Http404("Share not found")

        if not share.is_active:
            raise Http404("Share is no longer active")

        return share

    @extend_schema(
        summary="Access shared file",
        description="Access a file via share link",
    )
    def get(self, request, *args, **kwargs):
        """Get shared file information."""
        share = self.get_object()

        # Check password if required
        if share.password_protected:
            password = request.GET.get("password")
            if not password or not share.check_password(password):
                return Response(
                    {"error": "Password required or incorrect"},
                    status=status.HTTP_401_UNAUTHORIZED,
                )

        # Record access
        share.record_access(
            ip_address=request.META.get("REMOTE_ADDR"),
            user_agent=request.META.get("HTTP_USER_AGENT"),
        )

        # Return file information
        file_data = {
            "id": share.file.id,
            "name": share.file.original_name,
            "size": share.file.file_size,
            "human_readable_size": share.file.human_readable_size,
            "type": share.file.file_type,
            "mime_type": share.file.mime_type,
            "share_type": share.share_type,
            "can_download": share.share_type in ["download", "edit"],
            "download_url": f"/api/v1/files/share/{share.share_token}/download/",
        }

        return Response(file_data)


class FileShareDownloadView(generics.RetrieveAPIView):
    """Download view for shared files."""

    permission_classes = [drf_permissions.AllowAny]
    lookup_field = "share_token"

    def get_object(self):
        """Get file share by token."""
        share_token = self.kwargs["share_token"]
        try:
            share = FileShare.objects.get(share_token=share_token)
        except FileShare.DoesNotExist:
            raise Http404("Share not found")

        if not share.is_active:
            raise Http404("Share is no longer active")

        return share

    @extend_schema(
        summary="Download shared file",
        description="Download a file via share link",
    )
    def get(self, request, *args, **kwargs):
        """Download shared file."""
        share = self.get_object()

        # Check if download is allowed
        if share.share_type not in ["download", "edit"]:
            return Response(
                {"error": "Download not allowed for this share type"},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Check password if required
        if share.password_protected:
            password = request.GET.get("password")
            if not password or not share.check_password(password):
                return Response(
                    {"error": "Password required or incorrect"},
                    status=status.HTTP_401_UNAUTHORIZED,
                )

        # Record download
        share.record_download()

        # Return file
        file_upload = share.file
        if not file_upload.file or not os.path.exists(file_upload.file.path):
            raise Http404("File not found")

        response = FileResponse(
            open(file_upload.file.path, "rb"),
            content_type=file_upload.mime_type,
            as_attachment=True,
            filename=file_upload.original_name,
        )

        response["Content-Length"] = file_upload.file_size
        return response
