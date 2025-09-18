"""
Custom permission classes for organizations app.
"""
from rest_framework import permissions
from .models import Organization, Team, OrganizationMembership, TeamMembership


class IsOrganizationMember(permissions.BasePermission):
    """
    Permission that allows access only to organization members.
    """
    
    def has_permission(self, request, view):
        """Check if user is authenticated."""
        return request.user and request.user.is_authenticated
    
    def has_object_permission(self, request, view, obj):
        """Check if user is member of the organization."""
        if isinstance(obj, Organization):
            organization = obj
        elif hasattr(obj, 'organization'):
            organization = obj.organization
        elif hasattr(obj, 'team') and hasattr(obj.team, 'organization'):
            organization = obj.team.organization
        else:
            return False
        
        return OrganizationMembership.objects.filter(
            organization=organization,
            user=request.user,
            status='active'
        ).exists()


class IsOrganizationAdmin(permissions.BasePermission):
    """
    Permission that allows access only to organization owners/admins.
    """
    
    def has_permission(self, request, view):
        """Check if user is authenticated."""
        return request.user and request.user.is_authenticated
    
    def has_object_permission(self, request, view, obj):
        """Check if user is admin/owner of the organization."""
        if isinstance(obj, Organization):
            organization = obj
        elif hasattr(obj, 'organization'):
            organization = obj.organization
        elif hasattr(obj, 'team') and hasattr(obj.team, 'organization'):
            organization = obj.team.organization
        else:
            return False
        
        try:
            membership = OrganizationMembership.objects.get(
                organization=organization,
                user=request.user,
                status='active'
            )
            return membership.role in ['owner', 'admin']
        except OrganizationMembership.DoesNotExist:
            return False


class IsOrganizationOwner(permissions.BasePermission):
    """
    Permission that allows access only to organization owners.
    """
    
    def has_permission(self, request, view):
        """Check if user is authenticated."""
        return request.user and request.user.is_authenticated
    
    def has_object_permission(self, request, view, obj):
        """Check if user is owner of the organization."""
        if isinstance(obj, Organization):
            organization = obj
        elif hasattr(obj, 'organization'):
            organization = obj.organization
        elif hasattr(obj, 'team') and hasattr(obj.team, 'organization'):
            organization = obj.team.organization
        else:
            return False
        
        try:
            membership = OrganizationMembership.objects.get(
                organization=organization,
                user=request.user,
                status='active'
            )
            return membership.role == 'owner'
        except OrganizationMembership.DoesNotExist:
            return False


class IsTeamMember(permissions.BasePermission):
    """
    Permission that allows access only to team members.
    """
    
    def has_permission(self, request, view):
        """Check if user is authenticated."""
        return request.user and request.user.is_authenticated
    
    def has_object_permission(self, request, view, obj):
        """Check if user is member of the team."""
        if isinstance(obj, Team):
            team = obj
        elif hasattr(obj, 'team'):
            team = obj.team
        else:
            return False
        
        return TeamMembership.objects.filter(
            team=team,
            user=request.user,
            status='active'
        ).exists()


class IsTeamLeadOrOrganizationAdmin(permissions.BasePermission):
    """
    Permission that allows access to team leads or organization admins/owners.
    """
    
    def has_permission(self, request, view):
        """Check if user is authenticated."""
        return request.user and request.user.is_authenticated
    
    def has_object_permission(self, request, view, obj):
        """Check if user is team lead or organization admin/owner."""
        if isinstance(obj, Team):
            team = obj
        elif hasattr(obj, 'team'):
            team = obj.team
        else:
            return False
        
        # Check if user is team lead
        try:
            team_membership = TeamMembership.objects.get(
                team=team,
                user=request.user,
                status='active'
            )
            if team_membership.role == 'lead':
                return True
        except TeamMembership.DoesNotExist:
            pass
        
        # Check if user is organization admin/owner
        try:
            org_membership = OrganizationMembership.objects.get(
                organization=team.organization,
                user=request.user,
                status='active'
            )
            return org_membership.role in ['owner', 'admin']
        except OrganizationMembership.DoesNotExist:
            return False


class CanEditTeamDocuments(permissions.BasePermission):
    """
    Permission that allows document editing based on team role.
    """
    
    def has_permission(self, request, view):
        """Check if user is authenticated."""
        return request.user and request.user.is_authenticated
    
    def has_object_permission(self, request, view, obj):
        """Check if user can edit documents in the team."""
        if isinstance(obj, Team):
            team = obj
        elif hasattr(obj, 'team'):
            team = obj.team
        else:
            return False
        
        try:
            membership = TeamMembership.objects.get(
                team=team,
                user=request.user,
                status='active'
            )
            return membership.can_edit_documents
        except TeamMembership.DoesNotExist:
            return False


class OrganizationPermissionMixin:
    """
    Mixin to get organization from various contexts.
    """
    
    def get_organization(self, request, view, obj=None):
        """Get organization from object, view, or URL kwargs."""
        # From object
        if obj:
            if isinstance(obj, Organization):
                return obj
            elif hasattr(obj, 'organization'):
                return obj.organization
            elif hasattr(obj, 'team') and hasattr(obj.team, 'organization'):
                return obj.team.organization
        
        # From view
        if hasattr(view, 'get_organization'):
            return view.get_organization()
        
        # From URL kwargs
        org_id = view.kwargs.get('organization_id') or view.kwargs.get('org_id')
        if org_id:
            try:
                return Organization.objects.get(id=org_id)
            except Organization.DoesNotExist:
                pass
        
        return None
    
    def get_user_organization_role(self, user, organization):
        """Get user's role in organization."""
        try:
            membership = OrganizationMembership.objects.get(
                organization=organization,
                user=user,
                status='active'
            )
            return membership.role
        except OrganizationMembership.DoesNotExist:
            return None
    
    def get_user_team_role(self, user, team):
        """Get user's role in team."""
        try:
            membership = TeamMembership.objects.get(
                team=team,
                user=user,
                status='active'
            )
            return membership.role
        except TeamMembership.DoesNotExist:
            return None


class DynamicOrganizationPermission(OrganizationPermissionMixin, permissions.BasePermission):
    """
    Dynamic permission class that can be configured for different access levels.
    """
    
    def __init__(self, required_org_roles=None, required_team_roles=None, allow_self=False):
        """
        Initialize with required roles.
        
        Args:
            required_org_roles: List of required organization roles
            required_team_roles: List of required team roles  
            allow_self: Allow access to own user data
        """
        self.required_org_roles = required_org_roles or []
        self.required_team_roles = required_team_roles or []
        self.allow_self = allow_self
    
    def has_permission(self, request, view):
        """Check if user is authenticated."""
        return request.user and request.user.is_authenticated
    
    def has_object_permission(self, request, view, obj):
        """Check permissions based on configuration."""
        # Allow self access if configured
        if self.allow_self and hasattr(obj, 'user') and obj.user == request.user:
            return True
        
        organization = self.get_organization(request, view, obj)
        if not organization:
            return False
        
        # Check organization role requirements
        if self.required_org_roles:
            user_org_role = self.get_user_organization_role(request.user, organization)
            if user_org_role not in self.required_org_roles:
                return False
        
        # Check team role requirements
        if self.required_team_roles:
            if isinstance(obj, Team):
                team = obj
            elif hasattr(obj, 'team'):
                team = obj.team
            else:
                return False
            
            user_team_role = self.get_user_team_role(request.user, team)
            if user_team_role not in self.required_team_roles:
                return False
        
        return True
