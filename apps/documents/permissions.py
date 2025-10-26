"""
Permission classes for documents app.
"""

from rest_framework import permissions

from .models import Document


class IsDocumentReader(permissions.BasePermission):
    """
    Permission class for document read access.
    """

    def has_permission(self, request, view):
        """Check if user is authenticated."""
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        """Check if user can read the document."""
        if isinstance(obj, Document):
            return obj.can_read(request.user)
        return False


class IsDocumentWriter(permissions.BasePermission):
    """
    Permission class for document write access.
    """

    def has_permission(self, request, view):
        """Check if user is authenticated."""
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        """Check if user can write to the document."""
        if isinstance(obj, Document):
            return obj.can_write(request.user)
        return False


class IsDocumentAdmin(permissions.BasePermission):
    """
    Permission class for document admin access.
    """

    def has_permission(self, request, view):
        """Check if user is authenticated."""
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        """Check if user can administer the document."""
        if isinstance(obj, Document):
            return obj.can_admin(request.user)
        return False


class DocumentPermissionMixin:
    """
    Mixin to handle document permissions based on action.
    """

    def get_permissions(self):
        """
        Return the permission classes based on the action.
        """
        if self.action in ["list", "retrieve"]:
            permission_classes = [IsDocumentReader]
        elif self.action in ["create"]:
            permission_classes = [permissions.IsAuthenticated]
        elif self.action in ["update", "partial_update"]:
            permission_classes = [IsDocumentWriter]
        elif self.action in ["destroy", "permissions", "invite"]:
            permission_classes = [IsDocumentAdmin]
        else:
            permission_classes = [permissions.IsAuthenticated]

        return [permission() for permission in permission_classes]


class IsTeamMemberForDocument(permissions.BasePermission):
    """
    Permission class to check if user is a team member for document operations.
    """

    def has_permission(self, request, view):
        """Check if user is authenticated."""
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        """Check if user is a team member."""
        if isinstance(obj, Document):
            return obj.team.memberships.filter(
                user=request.user, status="active"
            ).exists()
        return False


class CanManageDocumentPermissions(permissions.BasePermission):
    """
    Permission class for managing document permissions.
    Only document admins and creators can manage permissions.
    """

    def has_permission(self, request, view):
        """Check if user is authenticated."""
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        """Check if user can manage document permissions."""
        if isinstance(obj, Document):
            return obj.can_admin(request.user)
        return False


class CanCommentOnDocument(permissions.BasePermission):
    """
    Permission class for commenting on documents.
    Users need at least read access to comment.
    """

    def has_permission(self, request, view):
        """Check if user is authenticated."""
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        """Check if user can comment on the document."""
        if isinstance(obj, Document):
            return obj.can_read(request.user)
        return False


class IsCommentOwnerOrDocumentAdmin(permissions.BasePermission):
    """
    Permission class for comment modification.
    Only comment owner or document admin can modify comments.
    """

    def has_permission(self, request, view):
        """Check if user is authenticated."""
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        """Check if user can modify the comment."""
        # For comment objects
        if hasattr(obj, "user") and hasattr(obj, "document"):
            return obj.user == request.user or obj.document.can_admin(request.user)
        return False


class CanCreateDocumentVersion(permissions.BasePermission):
    """
    Permission class for creating document versions.
    Users need write access to create versions.
    """

    def has_permission(self, request, view):
        """Check if user is authenticated."""
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        """Check if user can create versions for the document."""
        if isinstance(obj, Document):
            return obj.can_write(request.user)
        return False
