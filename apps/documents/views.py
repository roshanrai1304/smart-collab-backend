"""
API views for documents app.
"""

from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import permissions as drf_permissions
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from apps.organizations.models import Team

from .models import Document, DocumentComment, DocumentMedia
from .permissions import (
    CanCommentOnDocument,
    CanManageDocumentPermissions,
    DocumentPermissionMixin,
    IsDocumentReader,
)
from .serializers import (
    DocumentAutoSaveSerializer,
    DocumentCommentSerializer,
    DocumentCreateSerializer,
    DocumentDetailSerializer,
    DocumentListSerializer,
    DocumentMediaCreateSerializer,
    DocumentMediaSerializer,
    DocumentPermissionSerializer,
    DocumentPublishDraftSerializer,
    DocumentStatsSerializer,
    DocumentUpdateSerializer,
    DocumentVersionCreateSerializer,
    DocumentVersionSerializer,
)


@extend_schema_view(
    list=extend_schema(
        summary="List documents",
        description="Get all documents accessible to the user within their teams",
    ),
    create=extend_schema(
        summary="Create document",
        description="Create a new document within a team",
    ),
    retrieve=extend_schema(
        summary="Get document details",
        description="Get detailed information about a document",
    ),
    update=extend_schema(
        summary="Update document",
        description="Update document content and metadata",
    ),
    partial_update=extend_schema(
        summary="Partially update document",
        description="Partially update document fields",
    ),
    destroy=extend_schema(
        summary="Delete document",
        description="Delete a document (admin only)",
    ),
)
class DocumentViewSet(DocumentPermissionMixin, ModelViewSet):
    """ViewSet for document CRUD operations."""

    lookup_field = "id"

    def get_queryset(self):
        """Get documents accessible to the user."""
        user = self.request.user
        if not user.is_authenticated:
            return Document.objects.none()

        # Get user's teams
        user_teams = Team.objects.filter(
            memberships__user=user, memberships__status="active"
        )

        # Get documents from user's teams
        queryset = Document.objects.filter(team__in=user_teams)

        # Filter by team if specified
        team_id = self.request.query_params.get("team")
        if team_id:
            queryset = queryset.filter(team_id=team_id)

        # Filter by status if specified
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        # Filter by document type if specified
        doc_type = self.request.query_params.get("type")
        if doc_type:
            queryset = queryset.filter(document_type=doc_type)

        # Search by title or content
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) | Q(content__icontains=search)
            )

        # Filter by tags
        tags = self.request.query_params.get("tags")
        if tags:
            tag_list = [tag.strip() for tag in tags.split(",")]
            queryset = queryset.filter(tags__overlap=tag_list)

        return queryset.select_related(
            "team", "created_by", "updated_by"
        ).prefetch_related("permissions", "comments")

    def get_serializer_class(self):
        """Return appropriate serializer class."""
        if self.action == "list":
            return DocumentListSerializer
        elif self.action == "create":
            return DocumentCreateSerializer
        elif self.action in ["update", "partial_update"]:
            return DocumentUpdateSerializer
        else:
            return DocumentDetailSerializer

    def create(self, request, *args, **kwargs):
        """Create a document and return detailed response."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        document = serializer.save()

        # Return detailed document information
        detail_serializer = DocumentDetailSerializer(
            document, context={"request": request}
        )
        headers = self.get_success_headers(detail_serializer.data)
        return Response(
            detail_serializer.data, status=status.HTTP_201_CREATED, headers=headers
        )

    def update(self, request, *args, **kwargs):
        """Update a document and return detailed response."""
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        document = serializer.save()

        # Return detailed document information
        detail_serializer = DocumentDetailSerializer(
            document, context={"request": request}
        )
        return Response(detail_serializer.data)

    @action(detail=True, methods=["get", "post"], permission_classes=[IsDocumentReader])
    def versions(self, request, id=None):
        """Manage document versions."""
        document = self.get_object()

        if request.method == "GET":
            versions = document.versions.all()
            serializer = DocumentVersionSerializer(versions, many=True)
            return Response(serializer.data)

        elif request.method == "POST":
            # Check write permission for creating versions
            if not document.can_write(request.user):
                return Response(
                    {"error": "Write permission required to create versions"},
                    status=status.HTTP_403_FORBIDDEN,
                )

            serializer = DocumentVersionCreateSerializer(
                data=request.data, context={"request": request, "document": document}
            )
            if serializer.is_valid():
                version = serializer.save()
                return Response(
                    DocumentVersionSerializer(version).data,
                    status=status.HTTP_201_CREATED,
                )
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(
        detail=True,
        methods=["get"],
        url_path="versions/(?P<version_number>[^/.]+)",
        permission_classes=[IsDocumentReader],
    )
    def version_detail(self, request, id=None, version_number=None):
        """Get specific document version."""
        document = self.get_object()
        version = get_object_or_404(document.versions, version_number=version_number)
        serializer = DocumentVersionSerializer(version)
        return Response(serializer.data)

    @action(
        detail=True,
        methods=["get", "post"],
        permission_classes=[CanManageDocumentPermissions],
    )
    def permissions(self, request, id=None):
        """Manage document permissions."""
        document = self.get_object()

        if request.method == "GET":
            permissions_qs = document.permissions.all().select_related(
                "user", "granted_by"
            )
            serializer = DocumentPermissionSerializer(permissions_qs, many=True)
            return Response(serializer.data)

        elif request.method == "POST":
            serializer = DocumentPermissionSerializer(
                data=request.data, context={"request": request, "document": document}
            )
            if serializer.is_valid():
                permission = serializer.save()
                return Response(
                    DocumentPermissionSerializer(permission).data,
                    status=status.HTTP_201_CREATED,
                )
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(
        detail=True, methods=["get", "post"], permission_classes=[CanCommentOnDocument]
    )
    def comments(self, request, id=None):
        """Manage document comments."""
        document = self.get_object()

        if request.method == "GET":
            # Get top-level comments (not replies)
            comments = (
                document.comments.filter(parent_comment=None)
                .select_related("user", "resolved_by")
                .prefetch_related("replies__user")
            )
            serializer = DocumentCommentSerializer(
                comments, many=True, context={"request": request}
            )
            return Response(serializer.data)

        elif request.method == "POST":
            serializer = DocumentCommentSerializer(
                data=request.data, context={"request": request, "document": document}
            )
            if serializer.is_valid():
                comment = serializer.save()
                return Response(
                    DocumentCommentSerializer(
                        comment, context={"request": request}
                    ).data,
                    status=status.HTTP_201_CREATED,
                )
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(
        detail=False,
        methods=["get"],
        permission_classes=[drf_permissions.IsAuthenticated],
    )
    def stats(self, request):
        """Get document statistics for user's teams."""
        user = request.user
        user_teams = Team.objects.filter(
            memberships__user=user, memberships__status="active"
        )

        # Base queryset
        documents = Document.objects.filter(team__in=user_teams)

        # Calculate statistics
        stats = {
            "total_documents": documents.count(),
            "draft_documents": documents.filter(status="draft").count(),
            "published_documents": documents.filter(status="published").count(),
            "archived_documents": documents.filter(status="archived").count(),
            "total_words": documents.aggregate(Sum("word_count"))["word_count__sum"]
            or 0,
            "total_comments": DocumentComment.objects.filter(
                document__in=documents
            ).count(),
            "recent_activity_count": documents.filter(
                updated_at__gte=timezone.now() - timezone.timedelta(days=7)
            ).count(),
        }

        # Top contributors
        top_contributors = (
            documents.values("created_by__username", "created_by__first_name")
            .annotate(document_count=Count("id"))
            .order_by("-document_count")[:5]
        )

        stats["top_contributors"] = [
            {
                "username": contrib["created_by__username"],
                "name": contrib["created_by__first_name"],
                "document_count": contrib["document_count"],
            }
            for contrib in top_contributors
        ]

        serializer = DocumentStatsSerializer(stats)
        return Response(serializer.data)

    @action(
        detail=True,
        methods=["get", "post"],
        permission_classes=[IsDocumentReader],
        parser_classes=[MultiPartParser, FormParser],
    )
    def media(self, request, id=None):
        """Manage document media attachments."""
        document = self.get_object()

        if request.method == "GET":
            # Get all media attachments for the document
            media_attachments = document.media_attachments.all()
            serializer = DocumentMediaSerializer(media_attachments, many=True)
            return Response(serializer.data)

        elif request.method == "POST":
            # Check write permission for uploading media
            if not document.can_write(request.user):
                return Response(
                    {"error": "Write permission required to upload media"},
                    status=status.HTTP_403_FORBIDDEN,
                )

            serializer = DocumentMediaCreateSerializer(
                data=request.data, context={"request": request, "document": document}
            )
            if serializer.is_valid():
                media = serializer.save()
                return Response(
                    DocumentMediaSerializer(media).data,
                    status=status.HTTP_201_CREATED,
                )
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(
        detail=True,
        methods=["get", "patch", "delete"],
        url_path="media/(?P<media_id>[^/.]+)",
        permission_classes=[IsDocumentReader],
    )
    def media_detail(self, request, id=None, media_id=None):
        """Manage individual media attachment."""
        document = self.get_object()

        try:
            media = document.media_attachments.get(id=media_id)
        except DocumentMedia.DoesNotExist:
            return Response(
                {"error": "Media attachment not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if request.method == "GET":
            serializer = DocumentMediaSerializer(media)
            return Response(serializer.data)

        elif request.method == "PATCH":
            # Check write permission for updating media
            if not document.can_write(request.user):
                return Response(
                    {"error": "Write permission required to update media"},
                    status=status.HTTP_403_FORBIDDEN,
                )

            serializer = DocumentMediaSerializer(media, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        elif request.method == "DELETE":
            # Check admin permission for deleting media
            if (
                not document.can_admin(request.user)
                and media.uploaded_by != request.user
            ):
                return Response(
                    {
                        "error": "Permission denied. Only admins or uploaders can delete media"
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

            media.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)

    @action(
        detail=True,
        methods=["post"],
        url_path="auto-save",
        permission_classes=[IsDocumentReader],
    )
    def auto_save(self, request, id=None):
        """Auto-save document content as draft."""
        document = self.get_object()

        # Check write permission
        if not document.can_write(request.user):
            return Response(
                {"error": "Write permission required to auto-save"},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = DocumentAutoSaveSerializer(data=request.data)
        if serializer.is_valid():
            content = serializer.validated_data["content"]

            try:
                document.auto_save_draft(content, request.user)
                return Response(
                    {
                        "message": "Content auto-saved successfully",
                        "last_auto_save": document.last_auto_save,
                        "has_unsaved_changes": document.has_unsaved_changes,
                    },
                    status=status.HTTP_200_OK,
                )
            except Exception as e:
                return Response(
                    {"error": f"Auto-save failed: {str(e)}"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(
        detail=True,
        methods=["post"],
        url_path="publish-draft",
        permission_classes=[IsDocumentReader],
    )
    def publish_draft(self, request, id=None):
        """Publish draft content as the main document content."""
        document = self.get_object()

        # Check write permission
        if not document.can_write(request.user):
            return Response(
                {"error": "Write permission required to publish draft"},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = DocumentPublishDraftSerializer(data=request.data)
        if serializer.is_valid():
            create_version = serializer.validated_data.get("create_version", True)
            version_summary = serializer.validated_data.get("version_summary", "")

            if not document.has_unsaved_changes:
                return Response(
                    {"error": "No draft changes to publish"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            try:
                # Create version before publishing if requested
                if create_version and document.content:
                    document.create_version(request.user, version_summary)

                # Publish the draft
                success = document.publish_draft(request.user)

                if success:
                    return Response(
                        {
                            "message": "Draft published successfully",
                            "version_created": create_version,
                            "current_version": document.current_version,
                        },
                        status=status.HTTP_200_OK,
                    )
                else:
                    return Response(
                        {"error": "Failed to publish draft"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            except Exception as e:
                return Response(
                    {"error": f"Publish failed: {str(e)}"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(
        detail=True,
        methods=["post"],
        url_path="discard-draft",
        permission_classes=[IsDocumentReader],
    )
    def discard_draft(self, request, id=None):
        """Discard unsaved draft changes."""
        document = self.get_object()

        # Check write permission
        if not document.can_write(request.user):
            return Response(
                {"error": "Write permission required to discard draft"},
                status=status.HTTP_403_FORBIDDEN,
            )

        if not document.has_unsaved_changes:
            return Response(
                {"error": "No draft changes to discard"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            document.discard_draft()
            return Response(
                {"message": "Draft changes discarded successfully"},
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            return Response(
                {"error": f"Discard failed: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
