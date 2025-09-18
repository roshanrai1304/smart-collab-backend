"""
Authentication models for Smart Collaborative Backend.
"""
import uuid
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone 


class UserProfile(models.Model):
    """
    Extended user profile information.
    Extends Django's built-in User model with additional fields.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        'auth.User',
        on_delete=models.CASCADE,
        related_name='profile'
    )
    avatar_url = models.URLField(max_length=500, blank=True, null=True)
    user_timezone = models.CharField(max_length=50, default='UTC')
    preferences = models.JSONField(default=dict, blank=True)
    last_active = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'users_profile'
        indexes = [
            models.Index(fields=['user'], name='idx_users_profile_user_id'),
            models.Index(fields=['-last_active'], name='idx_users_profile_last_active'),
            models.Index(fields=['-created_at'], name='idx_users_profile_created_at'),
        ]

    def __str__(self):
        return f"{self.user.username}'s Profile"

    def update_last_active(self):
        """Update the last_active timestamp."""
        self.last_active = timezone.now()
        self.save(update_fields=['last_active'])


class RefreshToken(models.Model):
    """
    Custom refresh token model for JWT authentication.
    Tracks refresh tokens for better security and revocation.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        'auth.User',
        on_delete=models.CASCADE,
        related_name='refresh_tokens'
    )
    token = models.TextField()
    device_info = models.JSONField(default=dict, blank=True)  # Store device/browser info
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(default=timezone.now)
    last_used = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'auth_refresh_tokens'
        indexes = [
            models.Index(fields=['user', 'is_active'], name='idx_refresh_tokens_user_active'),
            models.Index(fields=['token'], name='idx_refresh_tokens_token'),
            models.Index(fields=['-created_at'], name='idx_refresh_tokens_created_at'),
            models.Index(fields=['expires_at'], name='idx_refresh_tokens_expires_at'),
        ]

    def __str__(self):
        return f"Refresh Token for {self.user.username}"

    def is_expired(self):
        """Check if the token is expired."""
        return timezone.now() > self.expires_at

    def revoke(self):
        """Revoke the token."""
        self.is_active = False
        self.save(update_fields=['is_active'])


class LoginAttempt(models.Model):
    """
    Track login attempts for security monitoring.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField()
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField(blank=True)
    success = models.BooleanField()
    failure_reason = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'auth_login_attempts'
        indexes = [
            models.Index(fields=['email', '-created_at'], name='idx_login_email_created'),
            models.Index(fields=['ip_address', '-created_at'], name='idx_login_attempts_ip_created'),
            models.Index(fields=['-created_at'], name='idx_login_attempts_created_at'),
            models.Index(fields=['success'], name='idx_login_attempts_success'),
        ]

    def __str__(self):
        status = "Success" if self.success else "Failed"
        return f"{status} login attempt for {self.email}"


class PasswordResetToken(models.Model):
    """
    Custom password reset tokens with expiration.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        'auth.User',
        on_delete=models.CASCADE,
        related_name='password_reset_tokens'
    )
    token = models.CharField(max_length=100, unique=True)
    is_used = models.BooleanField(default=False)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'auth_password_reset_tokens'
        indexes = [
            models.Index(fields=['token'], name='idx_password_reset_token'),
            models.Index(fields=['user', 'is_used'], name='idx_password_reset_user_used'),
            models.Index(fields=['expires_at'], name='idx_password_reset_expires'),
        ]

    def __str__(self):
        return f"Password reset token for {self.user.email}"

    def is_expired(self):
        """Check if the token is expired."""
        return timezone.now() > self.expires_at

    def use_token(self):
        """Mark the token as used."""
        self.is_used = True
        self.save(update_fields=['is_used'])


class EmailVerification(models.Model):
    """
    Email verification tokens for new user registrations.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        'auth.User',
        on_delete=models.CASCADE,
        related_name='email_verifications'
    )
    email = models.EmailField()
    token = models.CharField(max_length=100, unique=True)
    is_verified = models.BooleanField(default=False)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(default=timezone.now)
    verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'auth_email_verifications'
        indexes = [
            models.Index(fields=['token'], name='idx_email_verification_token'),
            models.Index(fields=['email', 'is_verified'], name='idx_email_verified'),
            models.Index(fields=['expires_at'], name='idx_email_verification_expires'),
        ]

    def __str__(self):
        return f"Email verification for {self.email}"

    def is_expired(self):
        """Check if the token is expired."""
        return timezone.now() > self.expires_at

    def verify_email(self):
        """Mark the email as verified."""
        self.is_verified = True
        self.verified_at = timezone.now()
        self.save(update_fields=['is_verified', 'verified_at'])