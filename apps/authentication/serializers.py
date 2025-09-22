"""
Authentication serializers for Smart Collaborative Backend.
"""

from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import EmailVerification, PasswordResetToken, UserProfile


class UserProfileSerializer(serializers.ModelSerializer):
    """Serializer for user profile information."""

    class Meta:
        model = UserProfile
        fields = [
            "id",
            "avatar_url",
            "user_timezone",
            "preferences",
            "last_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "last_active", "created_at", "updated_at"]


class UserSerializer(serializers.ModelSerializer):
    """Serializer for user information including profile."""

    profile = UserProfileSerializer(read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "is_active",
            "date_joined",
            "profile",
        ]
        read_only_fields = ["id", "date_joined"]


class UserRegistrationSerializer(serializers.ModelSerializer):
    """Serializer for user registration."""

    password = serializers.CharField(write_only=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True)
    user_timezone = serializers.CharField(max_length=50, default="UTC", required=False)

    class Meta:
        model = User
        fields = [
            "username",
            "email",
            "first_name",
            "last_name",
            "password",
            "password_confirm",
            "user_timezone",
        ]
        extra_kwargs = {
            "email": {"required": True},
            "first_name": {"required": True},
            "last_name": {"required": True},
        }

    def validate(self, attrs):
        """Validate password confirmation and email uniqueness."""
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError("Passwords don't match.")

        # Check if email already exists
        if User.objects.filter(email=attrs["email"]).exists():
            raise serializers.ValidationError("A user with this email already exists.")

        return attrs

    def create(self, validated_data):
        """Create user and profile."""
        user_timezone = validated_data.pop("user_timezone", "UTC")
        validated_data.pop("password_confirm", None)

        # Create user
        user = User.objects.create_user(
            username=validated_data["username"],
            email=validated_data["email"],
            first_name=validated_data["first_name"],
            last_name=validated_data["last_name"],
            password=validated_data["password"],
            is_active=False,  # Require email verification
        )

        # Update profile (created automatically by signals)
        if hasattr(user, "profile"):
            user.profile.user_timezone = user_timezone
            user.profile.save()
        else:
            # Fallback: create profile if signal didn't work
            UserProfile.objects.create(user=user, user_timezone=user_timezone)

        return user


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Custom JWT token serializer with additional user information."""

    def validate(self, attrs):
        """Validate credentials and add user info to response."""
        data = super().validate(attrs)

        # Add user information to token response
        user_serializer = UserSerializer(self.user)
        data["user"] = user_serializer.data

        # Update last active
        if hasattr(self.user, "profile"):
            self.user.profile.update_last_active()

        return data

    @classmethod
    def get_token(cls, user):
        """Add custom claims to token."""
        token = super().get_token(user)

        # Add custom claims
        token["username"] = user.username
        token["email"] = user.email
        token["full_name"] = f"{user.first_name} {user.last_name}".strip()

        return token


class LoginSerializer(serializers.Serializer):
    """Serializer for user login."""

    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    device_info = serializers.JSONField(required=False, default=dict)

    def validate(self, attrs):
        """Validate login credentials."""
        email = attrs.get("email")
        password = attrs.get("password")

        if email and password:
            # Find user by email
            try:
                user = User.objects.get(email=email)
                username = user.username
            except User.DoesNotExist:
                raise serializers.ValidationError("Invalid email or password.")

            # Authenticate user
            user = authenticate(username=username, password=password)

            if not user:
                raise serializers.ValidationError("Invalid email or password.")

            if not user.is_active:
                raise serializers.ValidationError("User account is disabled.")

            attrs["user"] = user
            return attrs
        else:
            raise serializers.ValidationError("Must include email and password.")


class PasswordChangeSerializer(serializers.Serializer):
    """Serializer for password change."""

    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(
        write_only=True, validators=[validate_password]
    )
    new_password_confirm = serializers.CharField(write_only=True)

    def validate(self, attrs):
        """Validate password change."""
        if attrs["new_password"] != attrs["new_password_confirm"]:
            raise serializers.ValidationError("New passwords don't match.")
        return attrs

    def validate_old_password(self, value):
        """Validate old password."""
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Old password is incorrect.")
        return value


class PasswordResetRequestSerializer(serializers.Serializer):
    """Serializer for password reset request."""

    email = serializers.EmailField()

    def validate_email(self, value):
        """Validate that user with this email exists."""
        try:
            User.objects.get(email=value)
        except User.DoesNotExist:
            # Don't reveal if email exists or not for security
            pass
        return value


class PasswordResetConfirmSerializer(serializers.Serializer):
    """Serializer for password reset confirmation."""

    token = serializers.CharField()
    new_password = serializers.CharField(
        write_only=True, validators=[validate_password]
    )
    new_password_confirm = serializers.CharField(write_only=True)

    def validate(self, attrs):
        """Validate password reset token and passwords."""
        if attrs["new_password"] != attrs["new_password_confirm"]:
            raise serializers.ValidationError("Passwords don't match.")

        # Validate token
        try:
            reset_token = PasswordResetToken.objects.get(
                token=attrs["token"], is_used=False
            )

            if reset_token.is_expired():
                raise serializers.ValidationError("Reset token has expired.")

            attrs["reset_token"] = reset_token

        except PasswordResetToken.DoesNotExist:
            raise serializers.ValidationError("Invalid reset token.")

        return attrs


class EmailVerificationSerializer(serializers.Serializer):
    """Serializer for email verification."""

    token = serializers.CharField()

    def validate_token(self, value):
        """Validate email verification token."""
        try:
            verification = EmailVerification.objects.get(token=value, is_verified=False)

            if verification.is_expired():
                raise serializers.ValidationError("Verification token has expired.")

            return verification

        except EmailVerification.DoesNotExist:
            raise serializers.ValidationError("Invalid verification token.")


class ResendVerificationSerializer(serializers.Serializer):
    """Serializer for resending email verification."""

    email = serializers.EmailField()

    def validate_email(self, value):
        """Validate that user exists and is not already verified."""
        try:
            user = User.objects.get(email=value)
            if user.is_active:
                raise serializers.ValidationError("Email is already verified.")
            return user
        except User.DoesNotExist:
            raise serializers.ValidationError("User with this email does not exist.")


class UserUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating user information."""

    profile = UserProfileSerializer(required=False)

    class Meta:
        model = User
        fields = ["first_name", "last_name", "profile"]

    def update(self, instance, validated_data):
        """Update user and profile information."""
        profile_data = validated_data.pop("profile", None)

        # Update user fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # Update profile fields
        if profile_data:
            profile = instance.profile
            for attr, value in profile_data.items():
                setattr(profile, attr, value)
            profile.save()

        return instance
