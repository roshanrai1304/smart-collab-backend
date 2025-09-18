"""
Custom managers for authentication models.
"""
from django.contrib.auth.models import BaseUserManager
from django.db import models
from django.utils import timezone


class UserProfileManager(models.Manager):
    """Custom manager for UserProfile model."""
    
    def create_profile(self, user, **extra_fields):
        """Create a user profile."""
        profile = self.model(user=user, **extra_fields)
        profile.save(using=self._db)
        return profile
    
    def active_users(self):
        """Get profiles of active users."""
        return self.filter(user__is_active=True)
    
    def recently_active(self, days=30):
        """Get profiles of users active in the last N days."""
        cutoff_date = timezone.now() - timezone.timedelta(days=days)
        return self.filter(last_active__gte=cutoff_date)


class RefreshTokenManager(models.Manager):
    """Custom manager for RefreshToken model."""
    
    def active_tokens(self):
        """Get active refresh tokens."""
        return self.filter(is_active=True, expires_at__gt=timezone.now())
    
    def expired_tokens(self):
        """Get expired refresh tokens."""
        return self.filter(expires_at__lte=timezone.now())
    
    def cleanup_expired(self):
        """Remove expired tokens."""
        return self.expired_tokens().delete()
    
    def revoke_user_tokens(self, user):
        """Revoke all tokens for a user."""
        return self.filter(user=user).update(is_active=False)


class LoginAttemptManager(models.Manager):
    """Custom manager for LoginAttempt model."""
    
    def successful_attempts(self):
        """Get successful login attempts."""
        return self.filter(success=True)
    
    def failed_attempts(self):
        """Get failed login attempts."""
        return self.filter(success=False)
    
    def recent_attempts(self, hours=24):
        """Get recent login attempts."""
        cutoff_time = timezone.now() - timezone.timedelta(hours=hours)
        return self.filter(created_at__gte=cutoff_time)
    
    def attempts_by_ip(self, ip_address, hours=24):
        """Get login attempts by IP address."""
        cutoff_time = timezone.now() - timezone.timedelta(hours=hours)
        return self.filter(
            ip_address=ip_address,
            created_at__gte=cutoff_time
        )
    
    def failed_attempts_by_ip(self, ip_address, hours=1):
        """Get failed attempts by IP in the last hour."""
        cutoff_time = timezone.now() - timezone.timedelta(hours=hours)
        return self.filter(
            ip_address=ip_address,
            success=False,
            created_at__gte=cutoff_time
        )


class PasswordResetTokenManager(models.Manager):
    """Custom manager for PasswordResetToken model."""
    
    def active_tokens(self):
        """Get active reset tokens."""
        return self.filter(is_used=False, expires_at__gt=timezone.now())
    
    def expired_tokens(self):
        """Get expired reset tokens."""
        return self.filter(expires_at__lte=timezone.now())
    
    def cleanup_expired(self):
        """Remove expired tokens."""
        return self.expired_tokens().delete()


class EmailVerificationManager(models.Manager):
    """Custom manager for EmailVerification model."""
    
    def pending_verifications(self):
        """Get pending email verifications."""
        return self.filter(is_verified=False, expires_at__gt=timezone.now())
    
    def expired_verifications(self):
        """Get expired verifications."""
        return self.filter(expires_at__lte=timezone.now())
    
    def cleanup_expired(self):
        """Remove expired verifications."""
        return self.expired_verifications().delete()
