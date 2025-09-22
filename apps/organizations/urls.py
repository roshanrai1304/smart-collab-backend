"""
URLs for organizations app.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    OrganizationViewSet,
    TeamViewSet,
    UserOrganizationsView,
    UserTeamsView,
)

# Create main router for organizations
router = DefaultRouter()
router.register(r"", OrganizationViewSet, basename="organization")

# Team URLs will be handled manually for now
team_patterns = [
    path(
        "<uuid:organization_id>/teams/",
        TeamViewSet.as_view({"get": "list", "post": "create"}),
        name="organization-teams-list",
    ),
    path(
        "<uuid:organization_id>/teams/<uuid:id>/",
        TeamViewSet.as_view(
            {
                "get": "retrieve",
                "put": "update",
                "patch": "partial_update",
                "delete": "destroy",
            }
        ),
        name="organization-teams-detail",
    ),
    path(
        "<uuid:organization_id>/teams/<uuid:id>/members/",
        TeamViewSet.as_view({"get": "members"}),
        name="organization-teams-members",
    ),
    path(
        "<uuid:organization_id>/teams/<uuid:id>/invite/",
        TeamViewSet.as_view({"post": "invite"}),
        name="organization-teams-invite",
    ),
]

urlpatterns = [
    # User-specific endpoints
    path(
        "user/organizations/",
        UserOrganizationsView.as_view(),
        name="user-organizations",
    ),
    path("user/teams/", UserTeamsView.as_view(), name="user-teams"),
    # Include router URLs
    path("", include(router.urls)),
    # Team URLs
    path("", include(team_patterns)),
]

# URL patterns generated:
# GET    /api/v1/organizations/                              - List user's organizations
# POST   /api/v1/organizations/                              - Create organization
# GET    /api/v1/organizations/{id}/                         - Get organization details
# PUT    /api/v1/organizations/{id}/                         - Update organization
# PATCH  /api/v1/organizations/{id}/                         - Partial update organization
# DELETE /api/v1/organizations/{id}/                         - Delete organization
# GET    /api/v1/organizations/{id}/stats/                   - Get organization stats
# GET    /api/v1/organizations/{id}/members/                 - List organization members
# POST   /api/v1/organizations/{id}/invite/                  - Invite user to organization

# GET    /api/v1/organizations/{org_id}/teams/               - List organization teams
# POST   /api/v1/organizations/{org_id}/teams/               - Create team
# GET    /api/v1/organizations/{org_id}/teams/{id}/          - Get team details
# PUT    /api/v1/organizations/{org_id}/teams/{id}/          - Update team
# PATCH  /api/v1/organizations/{org_id}/teams/{id}/          - Partial update team
# DELETE /api/v1/organizations/{org_id}/teams/{id}/          - Delete team
# GET    /api/v1/organizations/{org_id}/teams/{id}/members/  - List team members
# POST   /api/v1/organizations/{org_id}/teams/{id}/invite/   - Invite user to team

# GET    /api/v1/user/organizations/                         - List current user's organizations
# GET    /api/v1/user/teams/                                 - List current user's teams
