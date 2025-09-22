"""
API views for organizations app.
"""

from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import generics, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from .models import Organization, OrganizationMembership, Team, TeamMembership
from .permissions import (
    IsOrganizationAdmin,
    IsOrganizationMember,
    IsOrganizationOwner,
    IsTeamLeadOrOrganizationAdmin,
)
from .serializers import (
    OrganizationCreateSerializer,
    OrganizationInviteSerializer,
    OrganizationMembershipSerializer,
    OrganizationSerializer,
    OrganizationStatsSerializer,
    TeamCreateSerializer,
    TeamInviteSerializer,
    TeamMembershipSerializer,
    TeamSerializer,
)


@extend_schema_view(
    list=extend_schema(
        summary="List user's organizations",
        description="Get all organizations where the user is a member",
    ),
    create=extend_schema(
        summary="Create organization",
        description="Create a new organization with the user as owner",
    ),
    retrieve=extend_schema(
        summary="Get organization details",
        description="Get detailed information about an organization",
    ),
    update=extend_schema(
        summary="Update organization",
        description="Update organization details (admin/owner only)",
    ),
    partial_update=extend_schema(
        summary="Partially update organization",
        description="Partially update organization details (admin/owner only)",
    ),
    destroy=extend_schema(
        summary="Delete organization", description="Delete an organization (owner only)"
    ),
)
class OrganizationViewSet(ModelViewSet):
    """
    ViewSet for managing organizations.
    """

    serializer_class = OrganizationSerializer
    lookup_field = "id"

    def get_queryset(self):
        """Return organizations where user is a member."""
        if not self.request.user.is_authenticated:
            return Organization.objects.none()

        return (
            Organization.objects.filter(
                memberships__user=self.request.user, memberships__status="active"
            )
            .distinct()
            .select_related("created_by")
            .prefetch_related("memberships__user")
        )

    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == "create":
            return OrganizationCreateSerializer
        return OrganizationSerializer

    def get_permissions(self):
        """Return appropriate permissions based on action."""
        if self.action == "create":
            permission_classes = [permissions.IsAuthenticated]
        elif self.action in ["update", "partial_update"]:
            permission_classes = [IsOrganizationAdmin]
        elif self.action == "destroy":
            permission_classes = [IsOrganizationOwner]
        else:
            permission_classes = [IsOrganizationMember]

        return [permission() for permission in permission_classes]

    @extend_schema(
        summary="Get organization statistics",
        description="Get detailed statistics about the organization",
    )
    @action(detail=True, methods=["get"])
    def stats(self, request, id=None):
        """Get organization statistics."""
        organization = self.get_object()

        # Calculate statistics
        stats = {
            "member_count": organization.member_count,
            "team_count": organization.team_count,
            "document_count": 0,  # Will be implemented when documents app is ready
            "storage_used_gb": 0.0,  # Will be implemented with file storage
            "active_members_today": OrganizationMembership.objects.filter(
                organization=organization,
                status="active",
                last_accessed__date=timezone.now().date(),
            ).count(),
            "recent_activities": [],  # Will be implemented with activity tracking
        }

        serializer = OrganizationStatsSerializer(stats)
        return Response(serializer.data)

    @extend_schema(
        summary="List organization members",
        description="Get all members of the organization",
    )
    @action(detail=True, methods=["get"])
    def members(self, request, id=None):
        """List organization members."""
        organization = self.get_object()
        memberships = (
            OrganizationMembership.objects.filter(organization=organization)
            .select_related("user", "invited_by")
            .order_by("-created_at")
        )

        serializer = OrganizationMembershipSerializer(memberships, many=True)
        return Response(serializer.data)

    @extend_schema(
        summary="Invite user to organization",
        description="Invite a user to join the organization",
        request=OrganizationInviteSerializer,
    )
    @action(detail=True, methods=["post"], permission_classes=[IsOrganizationAdmin])
    def invite(self, request, id=None):
        """Invite user to organization."""
        organization = self.get_object()

        serializer = OrganizationInviteSerializer(
            data=request.data,
            context={"organization": organization, "request": request},
        )
        serializer.is_valid(raise_exception=True)
        membership = serializer.save()

        response_serializer = OrganizationMembershipSerializer(membership)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


@extend_schema_view(
    list=extend_schema(
        summary="List organization teams",
        description="Get all teams in the organization",
    ),
    create=extend_schema(
        summary="Create team", description="Create a new team in the organization"
    ),
    retrieve=extend_schema(
        summary="Get team details", description="Get detailed information about a team"
    ),
    update=extend_schema(
        summary="Update team",
        description="Update team details (team lead or org admin only)",
    ),
    partial_update=extend_schema(
        summary="Partially update team",
        description="Partially update team details (team lead or org admin only)",
    ),
    destroy=extend_schema(
        summary="Delete team", description="Delete a team (team lead or org admin only)"
    ),
)
class TeamViewSet(ModelViewSet):
    """
    ViewSet for managing teams within an organization.
    """

    serializer_class = TeamSerializer
    lookup_field = "id"

    def get_queryset(self):
        """Return teams in the organization where user is a member."""
        organization_id = self.kwargs.get("organization_id")
        if not organization_id or not self.request.user.is_authenticated:
            return Team.objects.none()

        # Check if user is organization member
        if not OrganizationMembership.objects.filter(
            organization_id=organization_id, user=self.request.user, status="active"
        ).exists():
            return Team.objects.none()

        return (
            Team.objects.filter(organization_id=organization_id, is_archived=False)
            .select_related("organization", "created_by")
            .prefetch_related("memberships__user")
        )

    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == "create":
            return TeamCreateSerializer
        return TeamSerializer

    def get_permissions(self):
        """Return appropriate permissions based on action."""
        if self.action == "create":
            permission_classes = [IsOrganizationMember]
        elif self.action in ["update", "partial_update", "destroy"]:
            permission_classes = [IsTeamLeadOrOrganizationAdmin]
        else:
            permission_classes = [IsOrganizationMember]

        return [permission() for permission in permission_classes]

    def get_organization(self):
        """Get organization from URL kwargs."""
        organization_id = self.kwargs.get("organization_id")
        return get_object_or_404(Organization, id=organization_id)

    def get_serializer_context(self):
        """Add organization to serializer context."""
        context = super().get_serializer_context()
        context["organization"] = self.get_organization()
        return context

    @extend_schema(
        summary="List team members", description="Get all members of the team"
    )
    @action(detail=True, methods=["get"])
    def members(self, request, organization_id=None, id=None):
        """List team members."""
        team = self.get_object()
        memberships = (
            TeamMembership.objects.filter(team=team)
            .select_related("user", "invited_by")
            .order_by("-created_at")
        )

        serializer = TeamMembershipSerializer(memberships, many=True)
        return Response(serializer.data)

    @extend_schema(
        summary="Invite user to team",
        description="Invite a user to join the team",
        request=TeamInviteSerializer,
    )
    @action(
        detail=True,
        methods=["post"],
        permission_classes=[IsTeamLeadOrOrganizationAdmin],
    )
    def invite(self, request, organization_id=None, id=None):
        """Invite user to team."""
        team = self.get_object()

        serializer = TeamInviteSerializer(
            data=request.data, context={"team": team, "request": request}
        )
        serializer.is_valid(raise_exception=True)
        membership = serializer.save()

        response_serializer = TeamMembershipSerializer(membership)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class UserOrganizationsView(generics.ListAPIView):
    """
    List all organizations where the current user is a member.
    """

    serializer_class = OrganizationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """Return user's organizations."""
        return (
            Organization.objects.filter(
                memberships__user=self.request.user, memberships__status="active"
            )
            .distinct()
            .select_related("created_by")
        )

    @extend_schema(
        summary="List user organizations",
        description="Get all organizations where the current user is a member",
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class UserTeamsView(generics.ListAPIView):
    """
    List all teams where the current user is a member.
    """

    serializer_class = TeamSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """Return user's teams."""
        return (
            Team.objects.filter(
                memberships__user=self.request.user,
                memberships__status="active",
                is_archived=False,
            )
            .distinct()
            .select_related("organization", "created_by")
        )

    @extend_schema(
        summary="List user teams",
        description="Get all teams where the current user is a member",
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)
