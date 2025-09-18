"""
Django admin configuration for authentication models.
"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from .models import (
    UserProfile, RefreshToken, LoginAttempt, 
    PasswordResetToken, EmailVerification
)


class UserProfileInline(admin.StackedInline):
    """Inline admin for user profile."""
    model = UserProfile
    can_delete = False
    verbose_name_plural = 'Profile'
    fields = ('avatar_url', 'user_timezone', 'preferences', 'last_active')
    readonly_fields = ('last_active',)


class UserAdmin(BaseUserAdmin):
    """Custom user admin with profile inline."""
    inlines = (UserProfileInline,)
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff', 'is_active', 'date_joined')
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'date_joined')
    search_fields = ('username', 'first_name', 'last_name', 'email')


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    """Admin for user profiles."""
    list_display = ('user', 'user_timezone', 'last_active', 'created_at')
    list_filter = ('user_timezone', 'created_at', 'last_active')
    search_fields = ('user__username', 'user__email', 'user__first_name', 'user__last_name')
    readonly_fields = ('id', 'created_at', 'updated_at')
    raw_id_fields = ('user',)


@admin.register(RefreshToken)
class RefreshTokenAdmin(admin.ModelAdmin):
    """Admin for refresh tokens."""
    list_display = ('user', 'ip_address', 'is_active', 'expires_at', 'created_at')
    list_filter = ('is_active', 'created_at', 'expires_at')
    search_fields = ('user__username', 'user__email', 'ip_address')
    readonly_fields = ('id', 'token', 'created_at', 'last_used')
    raw_id_fields = ('user',)
    
    def has_add_permission(self, request):
        return False


@admin.register(LoginAttempt)
class LoginAttemptAdmin(admin.ModelAdmin):
    """Admin for login attempts."""
    list_display = ('email', 'ip_address', 'success', 'failure_reason', 'created_at')
    list_filter = ('success', 'created_at')
    search_fields = ('email', 'ip_address')
    readonly_fields = ('id', 'created_at')
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False


@admin.register(PasswordResetToken)
class PasswordResetTokenAdmin(admin.ModelAdmin):
    """Admin for password reset tokens."""
    list_display = ('user', 'is_used', 'expires_at', 'created_at')
    list_filter = ('is_used', 'created_at', 'expires_at')
    search_fields = ('user__username', 'user__email')
    readonly_fields = ('id', 'token', 'created_at')
    raw_id_fields = ('user',)
    
    def has_add_permission(self, request):
        return False


@admin.register(EmailVerification)
class EmailVerificationAdmin(admin.ModelAdmin):
    """Admin for email verifications."""
    list_display = ('user', 'email', 'is_verified', 'expires_at', 'created_at')
    list_filter = ('is_verified', 'created_at', 'expires_at')
    search_fields = ('user__username', 'email')
    readonly_fields = ('id', 'token', 'created_at', 'verified_at')
    raw_id_fields = ('user',)
    
    def has_add_permission(self, request):
        return False


# Re-register UserAdmin
admin.site.unregister(User)
admin.site.register(User, UserAdmin)