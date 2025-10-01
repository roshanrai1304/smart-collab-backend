"""
Permission classes for files app.
"""

from rest_framework import permissions

from .models import FileUpload


class IsFileReader(permissions.BasePermission):
    """
    Permission class for file read access.
    """

    def has_permission(self, request, view):
        """Check if user is authenticated."""
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        """Check if user can read the file."""
        if isinstance(obj, FileUpload):
            return obj.can_read(request.user)
        return False


class IsFileWriter(permissions.BasePermission):
    """
    Permission class for file write access.
    """

    def has_permission(self, request, view):
        """Check if user is authenticated."""
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        """Check if user can write to the file."""
        if isinstance(obj, FileUpload):
            return obj.can_write(request.user)
        return False


class IsFileAdmin(permissions.BasePermission):
    """
    Permission class for file admin access.
    """

    def has_permission(self, request, view):
        """Check if user is authenticated."""
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        """Check if user can administer the file."""
        if isinstance(obj, FileUpload):
            return obj.can_admin(request.user)
        return False


class FilePermissionMixin:
    """
    Mixin to handle file permissions based on action.
    """

    def get_permissions(self):
        """
        Return the permission classes based on the action.
        """
        if self.action in ["list", "retrieve", "download", "preview"]:
            permission_classes = [IsFileReader]
        elif self.action in ["create", "upload"]:
            permission_classes = [permissions.IsAuthenticated]
        elif self.action in ["update", "partial_update", "attach_to_document"]:
            permission_classes = [IsFileWriter]
        elif self.action in ["destroy", "permissions", "shares", "delete_from_storage"]:
            permission_classes = [IsFileAdmin]
        else:
            permission_classes = [permissions.IsAuthenticated]

        return [permission() for permission in permission_classes]


class IsTeamMemberForFile(permissions.BasePermission):
    """
    Permission class to check if user is a team member for file operations.
    """

    def has_permission(self, request, view):
        """Check if user is authenticated."""
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        """Check if user is a team member."""
        if isinstance(obj, FileUpload):
            return obj.team.memberships.filter(
                user=request.user, status="active"
            ).exists()
        return False


class CanManageFilePermissions(permissions.BasePermission):
    """
    Permission class for managing file permissions.
    Only file admins and uploaders can manage permissions.
    """

    def has_permission(self, request, view):
        """Check if user is authenticated."""
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        """Check if user can manage file permissions."""
        if isinstance(obj, FileUpload):
            return obj.can_admin(request.user)
        return False


class CanCreateFileShares(permissions.BasePermission):
    """
    Permission class for creating file shares.
    Users need at least write access to create shares.
    """

    def has_permission(self, request, view):
        """Check if user is authenticated."""
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        """Check if user can create shares for the file."""
        if isinstance(obj, FileUpload):
            return obj.can_write(request.user)
        return False


class IsFileUploaderOrAdmin(permissions.BasePermission):
    """
    Permission class for file uploader or admin access.
    Only file uploader or admins can perform certain operations.
    """

    def has_permission(self, request, view):
        """Check if user is authenticated."""
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        """Check if user is the uploader or admin."""
        if isinstance(obj, FileUpload):
            return obj.uploaded_by == request.user or obj.can_admin(request.user)
        return False


class IsVirusScanClean(permissions.BasePermission):
    """
    Permission class to check if file passed virus scan.
    """

    def has_permission(self, request, view):
        """Always allow at permission level."""
        return True

    def has_object_permission(self, request, view, obj):
        """Check if file is safe to access."""
        if isinstance(obj, FileUpload):
            # Allow admins to access even infected files for management
            if obj.can_admin(request.user):
                return True
            # For regular users, file must be clean
            return obj.is_safe
        return True
