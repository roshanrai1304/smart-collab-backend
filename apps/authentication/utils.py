"""
Authentication utility functions.
"""

from django.conf import settings
from django.core.mail import send_mail


def get_client_ip(request):
    """Get client IP address from request."""
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        ip = x_forwarded_for.split(",")[0]
    else:
        ip = request.META.get("REMOTE_ADDR")
    return ip


def send_verification_email(email, token):
    """Send email verification email."""
    subject = "Verify your Smart Collab account"
    # Use backend URL for email verification link
    backend_url = getattr(settings, "BACKEND_URL", "http://localhost:8000")
    verification_url = f"{backend_url}/api/v1/auth/verify-email/?token={token}"

    message = f"""
    Welcome to Smart Collab!

    Please click the link below to verify your email address:
    {verification_url}

    This link will expire in 7 days.

    If you didn't create an account, please ignore this email.
    """

    send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        [email],
        fail_silently=False,
    )


def send_password_reset_email(email, token):
    """Send password reset email."""
    subject = "Reset your Smart Collab password"
    reset_url = f"{settings.FRONTEND_URL}/reset-password?token={token}"

    message = f"""
    You requested a password reset for your Smart Collab account.

    Please click the link below to reset your password:
    {reset_url}

    This link will expire in 1 hour.

    If you didn't request this reset, please ignore this email.
    """

    send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        [email],
        fail_silently=False,
    )
