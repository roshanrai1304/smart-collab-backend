"""
API views for collaboration app.
"""

from datetime import timedelta

from django.utils import timezone
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import generics
from rest_framework import permissions as drf_permissions
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet
from rest_framework_simplejwt.tokens import RefreshToken

from apps.organizations.models import Team

from .models import CollaborationActivity, CollaborationRoom, CollaborationSession
from .serializers import (
    CollaborationRoomCreateSerializer,
    CollaborationRoomDetailSerializer,
    CollaborationRoomListSerializer,
    CollaborationRoomUpdateSerializer,
    CollaborationSessionSerializer,
    CollaborationStatsSerializer,
    JoinRoomSerializer,
    WebSocketTokenSerializer,
)


@extend_schema_view(
    list=extend_schema(
        summary="List collaboration rooms",
        description="Get all collaboration rooms accessible to the user",
    ),
    create=extend_schema(
        summary="Create collaboration room",
        description="Create a new collaboration room for a document",
    ),
    retrieve=extend_schema(
        summary="Get collaboration room details",
        description="Get detailed information about a collaboration room",
    ),
    update=extend_schema(
        summary="Update collaboration room",
        description="Update collaboration room settings",
    ),
    destroy=extend_schema(
        summary="Delete collaboration room",
        description="Delete a collaboration room",
    ),
)
class CollaborationRoomViewSet(ModelViewSet):
    """ViewSet for collaboration room management."""

    lookup_field = "id"

    def get_queryset(self):
        """Get collaboration rooms accessible to the user."""
        user = self.request.user
        if not user.is_authenticated:
            return CollaborationRoom.objects.none()

        # Get user's teams
        user_teams = Team.objects.filter(
            memberships__user=user, memberships__status="active"
        )

        # Get rooms from user's teams
        queryset = CollaborationRoom.objects.filter(team__in=user_teams)

        # Apply filters
        queryset = self._apply_filters(queryset)

        return queryset.select_related(
            "document", "team", "created_by"
        ).prefetch_related("sessions", "activities")

    def _apply_filters(self, queryset):
        """Apply query parameter filters."""
        # Filter by document
        document_id = self.request.query_params.get("document")
        if document_id:
            queryset = queryset.filter(document_id=document_id)

        # Filter by room type
        room_type = self.request.query_params.get("type")
        if room_type:
            queryset = queryset.filter(room_type=room_type)

        # Filter by status
        room_status = self.request.query_params.get("status")
        if room_status:
            queryset = queryset.filter(status=room_status)

        # Filter by public/private
        is_public = self.request.query_params.get("public")
        if is_public is not None:
            queryset = queryset.filter(is_public=is_public.lower() == "true")

        return queryset

    def get_serializer_class(self):
        """Return appropriate serializer class."""
        if self.action == "list":
            return CollaborationRoomListSerializer
        elif self.action == "create":
            return CollaborationRoomCreateSerializer
        elif self.action in ["update", "partial_update"]:
            return CollaborationRoomUpdateSerializer
        else:
            return CollaborationRoomDetailSerializer

    def create(self, request, *args, **kwargs):
        """Create a collaboration room and return detailed response."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        room = serializer.save()

        # Return detailed room information
        detail_serializer = CollaborationRoomDetailSerializer(
            room, context={"request": request}
        )
        headers = self.get_success_headers(detail_serializer.data)
        return Response(
            detail_serializer.data, status=status.HTTP_201_CREATED, headers=headers
        )

    @action(detail=True, methods=["post"])
    def join(self, request, id=None):
        """Join a collaboration room."""
        room = self.get_object()

        serializer = JoinRoomSerializer(
            data=request.data, context={"request": request, "room": room}
        )
        serializer.is_valid(raise_exception=True)

        # Create or get session
        session, created = CollaborationSession.objects.get_or_create(
            room=room,
            user=request.user,
            defaults={
                "user_role": serializer.validated_data["user_role"],
                "client_info": serializer.validated_data.get("client_info", {}),
                "ip_address": request.META.get("REMOTE_ADDR"),
                "user_agent": request.META.get("HTTP_USER_AGENT", ""),
            },
        )

        if not created:
            # Update existing session
            session.status = "active"
            session.user_role = serializer.validated_data["user_role"]
            session.last_seen = timezone.now()
            session.save()

        return Response(
            {
                "message": "Successfully joined room",
                "session": CollaborationSessionSerializer(session).data,
                "websocket_url": f"/ws/collaboration/{room.id}/",
            }
        )

    @action(detail=True, methods=["get"])
    def sessions(self, request, id=None):
        """Get active sessions in the room."""
        room = self.get_object()
        active_sessions = room.get_active_sessions()

        serializer = CollaborationSessionSerializer(active_sessions, many=True)
        return Response(serializer.data)

    @action(
        detail=False,
        methods=["get"],
        permission_classes=[drf_permissions.IsAuthenticated],
    )
    def stats(self, request):
        """Get collaboration statistics for user's teams."""
        user = request.user
        user_teams = Team.objects.filter(
            memberships__user=user, memberships__status="active"
        )

        # Base queryset
        rooms = CollaborationRoom.objects.filter(team__in=user_teams)
        sessions = CollaborationSession.objects.filter(room__in=rooms)
        activities = CollaborationActivity.objects.filter(room__in=rooms)

        # Calculate statistics
        stats = {
            "total_rooms": rooms.count(),
            "active_rooms": rooms.filter(status="active").count(),
            "total_sessions": sessions.count(),
            "active_sessions": sessions.filter(
                status="active", last_seen__gte=timezone.now() - timedelta(minutes=5)
            ).count(),
            "total_activities": activities.count(),
            "recent_activities_count": activities.filter(
                server_timestamp__gte=timezone.now() - timedelta(hours=24)
            ).count(),
        }

        serializer = CollaborationStatsSerializer(stats)
        return Response(serializer.data)


class WebSocketTokenView(generics.GenericAPIView):
    """Generate WebSocket authentication token for collaboration."""

    permission_classes = [drf_permissions.IsAuthenticated]
    serializer_class = WebSocketTokenSerializer

    @extend_schema(
        summary="Get WebSocket token",
        description="Generate authentication token for WebSocket connection to collaboration room",
    )
    def post(self, request):
        """Generate WebSocket authentication token."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        room_id = serializer.validated_data["room_id"]

        # Generate JWT token for WebSocket authentication
        refresh = RefreshToken.for_user(request.user)
        access_token = str(refresh.access_token)

        return Response(
            {
                "token": access_token,
                "websocket_url": f"/ws/collaboration/{room_id}/",
                "expires_in": 3600,  # 1 hour
            }
        )
