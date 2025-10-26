"""
Authentication views for Smart Collaborative Backend.
"""

import secrets
from datetime import timedelta

from django.contrib.auth.models import User
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import EmailVerification, LoginAttempt
from .serializers import (
    CustomTokenObtainPairSerializer,
    EmailVerificationSerializer,
    PasswordChangeSerializer,
    ResendVerificationSerializer,
    UserOrganizationTeamSerializer,
    UserRegistrationSerializer,
    UserSerializer,
    UserUpdateSerializer,
)
from .utils import get_client_ip, send_verification_email


class RegisterView(generics.CreateAPIView):
    """User registration endpoint."""

    queryset = User.objects.all()
    serializer_class = UserRegistrationSerializer
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        summary="Register new user",
        description="Create a new user account. Email verification required before activation.",
        responses={201: UserSerializer, 400: "Validation errors"},
    )
    def post(self, request, *args, **kwargs):
        """Create new user and send verification email."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        # Create email verification token
        verification_token = secrets.token_urlsafe(32)
        EmailVerification.objects.create(
            user=user,
            email=user.email,
            token=verification_token,
            expires_at=timezone.now() + timedelta(days=7),
        )

        # Send verification email
        send_verification_email(user.email, verification_token)

        return Response(
            {
                "message": "User registered successfully. Please check your email for verification.",
                "user": UserSerializer(user).data,
            },
            status=status.HTTP_201_CREATED,
        )


class CustomTokenObtainPairView(TokenObtainPairView):
    """Custom JWT token obtain view with login tracking."""

    serializer_class = CustomTokenObtainPairSerializer

    @extend_schema(
        summary="Obtain JWT token pair",
        description="Login with email/password and get access/refresh tokens",
        responses={200: "Token pair with user information", 401: "Invalid credentials"},
    )
    def post(self, request, *args, **kwargs):
        """Login user and return tokens with user info."""
        ip_address = get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")
        email = request.data.get("username", "")

        try:
            response = super().post(request, *args, **kwargs)

            # Log successful login
            LoginAttempt.objects.create(
                email=email, ip_address=ip_address, user_agent=user_agent, success=True
            )

            return response

        except Exception as e:
            # Log failed login
            LoginAttempt.objects.create(
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
                success=False,
                failure_reason=str(e)[:100],
            )
            raise


class ProfileView(generics.RetrieveUpdateAPIView):
    """User profile view."""

    serializer_class = UserUpdateSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user

    @extend_schema(
        summary="Get user profile",
        description="Get current user profile information",
        responses={200: UserSerializer},
    )
    def get(self, request, *args, **kwargs):
        """Get user profile."""
        user = self.get_object()
        serializer = UserSerializer(user)
        return Response(serializer.data)


class PasswordChangeView(APIView):
    """Password change endpoint."""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="Change password",
        description="Change user password",
        request=PasswordChangeSerializer,
        responses={200: "Password changed successfully", 400: "Validation errors"},
    )
    def post(self, request):
        """Change user password."""
        serializer = PasswordChangeSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)

        # Change password
        request.user.set_password(serializer.validated_data["new_password"])
        request.user.save()

        return Response({"message": "Password changed successfully"})


@extend_schema(
    summary="Get current user",
    description="Get current authenticated user information",
    responses={200: UserSerializer},
)
@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def current_user(request):
    """Get current user information."""
    serializer = UserSerializer(request.user)
    return Response(serializer.data)


class EmailVerificationView(generics.GenericAPIView):
    """Email verification endpoint."""

    serializer_class = EmailVerificationSerializer
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        summary="Verify email address (GET)",
        description="Verify user email address using verification token from URL parameter",
        responses={200: "Email verified successfully", 400: "Invalid token"},
    )
    def get(self, request):
        """Verify email with token from URL parameter."""
        token = request.GET.get("token")
        if not token:
            return Response(
                {"error": "Token parameter is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return self._verify_token(token)

    @extend_schema(
        summary="Verify email address (POST)",
        description="Verify user email address using verification token in request body",
        responses={200: "Email verified successfully", 400: "Invalid token"},
    )
    def post(self, request):
        """Verify email with token from request body."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # The serializer already validates and returns the verification object
        verification = serializer.validated_data["token"]

        return self._verify_token_object(verification)

    def _verify_token(self, token):
        """Verify token and activate user."""
        try:
            verification = EmailVerification.objects.get(token=token, is_verified=False)

            if verification.is_expired():
                return Response(
                    {
                        "error": "Verification token has expired. Please request a new verification email."
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            return self._verify_token_object(verification)

        except EmailVerification.DoesNotExist:
            return Response(
                {"error": "Invalid verification token."},
                status=status.HTTP_400_BAD_REQUEST,
            )

    def _verify_token_object(self, verification):
        """Common verification logic."""
        # Verify email and activate user
        verification.verify_email()
        user = verification.user
        user.is_active = True
        user.save()

        return Response(
            {
                "message": "Email verified successfully! Your account is now active and you can login.",
                "user": UserSerializer(user).data,
                "redirect_message": "You can now close this page and login to Smart Collab.",
            }
        )


class ResendVerificationView(generics.GenericAPIView):
    """Resend email verification endpoint."""

    serializer_class = ResendVerificationSerializer
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        summary="Resend verification email",
        description="Resend verification email to user",
        responses={
            200: "Verification email sent",
            400: "User not found or already verified",
        },
    )
    def post(self, request):
        """Resend verification email."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # The serializer already validates and returns the user object
        user = serializer.validated_data["email"]

        # Delete old verification tokens
        EmailVerification.objects.filter(user=user).delete()

        # Create new verification token
        verification_token = secrets.token_urlsafe(32)
        EmailVerification.objects.create(
            user=user,
            email=user.email,
            token=verification_token,
            expires_at=timezone.now() + timedelta(days=7),
        )

        # Send verification email
        send_verification_email(user.email, verification_token)

        return Response({"message": "Verification email sent successfully"})


class UserOrganizationTeamView(generics.RetrieveAPIView):
    """
    Get user's organizations and teams details.
    Returns comprehensive information about user's memberships.
    """

    serializer_class = UserOrganizationTeamSerializer
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="Get user organizations and teams",
        description="Retrieve detailed information about organizations and teams the user belongs to, "
        "including roles, permissions, and statistics.",
        responses={
            200: UserOrganizationTeamSerializer,
            401: "Authentication required",
        },
    )
    def get(self, request):
        """Get user's organizations and teams details."""
        user = request.user
        serializer = self.get_serializer(user)
        return Response(serializer.data)
