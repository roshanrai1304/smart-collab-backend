"""
Serializers for organizations app.
"""

from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify
from rest_framework import serializers

from .models import Organization, OrganizationMembership, Team, TeamMembership


class UserBasicSerializer(serializers.ModelSerializer):
    """Basic user information for organization/team contexts."""

    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "username", "email", "first_name", "last_name", "full_name"]
        read_only_fields = ["id", "username", "email"]

    def get_full_name(self, obj):
        return f"{obj.first_name} {obj.last_name}".strip() or obj.username


class OrganizationSerializer(serializers.ModelSerializer):
    """Serializer for Organization model."""

    member_count = serializers.ReadOnlyField()
    team_count = serializers.ReadOnlyField()
    created_by = UserBasicSerializer(read_only=True)
    can_add_member = serializers.ReadOnlyField()

    class Meta:
        model = Organization
        fields = [
            "id",
            "name",
            "slug",
            "domain",
            "description",
            "logo_url",
            "subscription_plan",
            "subscription_status",
            "max_members",
            "max_documents",
            "max_storage_gb",
            "settings",
            "member_count",
            "team_count",
            "can_add_member",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "member_count",
            "team_count",
            "can_add_member",
            "created_by",
            "created_at",
            "updated_at",
        ]

    def validate_slug(self, value):
        """Ensure slug is unique."""
        if self.instance:
            # Update case - exclude current instance
            if (
                Organization.objects.filter(slug=value)
                .exclude(pk=self.instance.pk)
                .exists()
            ):
                raise serializers.ValidationError(
                    "Organization with this slug already exists."
                )
        else:
            # Create case
            if Organization.objects.filter(slug=value).exists():
                raise serializers.ValidationError(
                    "Organization with this slug already exists."
                )
        return value

    def create(self, validated_data):
        """Create organization with current user as owner."""
        validated_data["created_by"] = self.context["request"].user

        # Auto-generate slug if not provided
        if not validated_data.get("slug"):
            validated_data["slug"] = slugify(validated_data["name"])

        return super().create(validated_data)


class OrganizationCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating organizations."""

    class Meta:
        model = Organization
        fields = ["name", "slug", "domain", "description", "logo_url"]

    def validate_slug(self, value):
        """Ensure slug is unique."""
        if Organization.objects.filter(slug=value).exists():
            raise serializers.ValidationError(
                "Organization with this slug already exists."
            )
        return value

    def create(self, validated_data):
        """Create organization with current user as owner."""
        validated_data["created_by"] = self.context["request"].user

        # Auto-generate slug if not provided
        if not validated_data.get("slug"):
            validated_data["slug"] = slugify(validated_data["name"])

        return super().create(validated_data)


class TeamSerializer(serializers.ModelSerializer):
    """Serializer for Team model."""

    member_count = serializers.ReadOnlyField()
    organization = OrganizationSerializer(read_only=True)
    created_by = UserBasicSerializer(read_only=True)
    user_role = serializers.SerializerMethodField()

    class Meta:
        model = Team
        fields = [
            "id",
            "organization",
            "name",
            "slug",
            "description",
            "color",
            "settings",
            "is_default",
            "is_archived",
            "member_count",
            "user_role",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "organization",
            "member_count",
            "user_role",
            "created_by",
            "created_at",
            "updated_at",
        ]

    def get_user_role(self, obj):
        """Get current user's role in this team."""
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            return obj.get_user_role(request.user)
        return None

    def validate_slug(self, value):
        """Ensure slug is unique within organization."""
        organization = self.context.get("organization")
        if not organization:
            # This should be set by the view
            raise serializers.ValidationError("Organization context required.")

        query = Team.objects.filter(organization=organization, slug=value)
        if self.instance:
            query = query.exclude(pk=self.instance.pk)

        if query.exists():
            raise serializers.ValidationError(
                "Team with this slug already exists in the organization."
            )
        return value


class TeamCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating teams."""

    class Meta:
        model = Team
        fields = ["name", "slug", "description", "color"]

    def validate_slug(self, value):
        """Ensure slug is unique within organization."""
        organization = self.context.get("organization")
        if not organization:
            raise serializers.ValidationError("Organization context required.")

        if Team.objects.filter(organization=organization, slug=value).exists():
            raise serializers.ValidationError(
                "Team with this slug already exists in the organization."
            )
        return value

    def create(self, validated_data):
        """Create team with organization and current user."""
        validated_data["organization"] = self.context["organization"]
        validated_data["created_by"] = self.context["request"].user

        # Auto-generate slug if not provided
        if not validated_data.get("slug"):
            validated_data["slug"] = slugify(validated_data["name"])

        return super().create(validated_data)


class OrganizationMembershipSerializer(serializers.ModelSerializer):
    """Serializer for OrganizationMembership model."""

    user = UserBasicSerializer(read_only=True)
    organization = OrganizationSerializer(read_only=True)
    invited_by = UserBasicSerializer(read_only=True)

    class Meta:
        model = OrganizationMembership
        fields = [
            "id",
            "organization",
            "user",
            "role",
            "status",
            "invited_by",
            "invited_at",
            "joined_at",
            "last_accessed",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "organization",
            "user",
            "invited_by",
            "invited_at",
            "joined_at",
            "last_accessed",
            "created_at",
        ]


class OrganizationInviteSerializer(serializers.Serializer):
    """Serializer for inviting users to organization."""

    email = serializers.EmailField()
    role = serializers.ChoiceField(
        choices=OrganizationMembership.ROLES, default="member"
    )

    def validate_email(self, value):
        """Validate that user exists."""
        try:
            user = User.objects.get(email=value)
            self.user = user  # Store for later use
            return value
        except User.DoesNotExist:
            raise serializers.ValidationError("User with this email does not exist.")

    def validate(self, attrs):
        """Check if user is already a member."""
        organization = self.context["organization"]

        if OrganizationMembership.objects.filter(
            organization=organization, user=self.user
        ).exists():
            raise serializers.ValidationError(
                "User is already a member of this organization."
            )

        # Check member limit
        if not organization.can_add_member():
            raise serializers.ValidationError(
                "Organization has reached its member limit."
            )

        return attrs

    def save(self):
        """Create the membership."""
        organization = self.context["organization"]
        invited_by = self.context["request"].user

        with transaction.atomic():
            membership = OrganizationMembership.objects.create(
                organization=organization,
                user=self.user,
                role=self.validated_data["role"],
                status="invited",
                invited_by=invited_by,
                invited_at=timezone.now(),
            )

            # Add to default team if membership is active
            if membership.status == "active":
                default_team = organization.get_default_team()
                TeamMembership.objects.get_or_create(
                    team=default_team,
                    user=self.user,
                    defaults={
                        "role": "viewer",
                        "status": "active",
                    },
                )

        return membership


class TeamMembershipSerializer(serializers.ModelSerializer):
    """Serializer for TeamMembership model."""

    user = UserBasicSerializer(read_only=True)
    team = TeamSerializer(read_only=True)
    invited_by = UserBasicSerializer(read_only=True)
    organization_role = serializers.SerializerMethodField()

    class Meta:
        model = TeamMembership
        fields = [
            "id",
            "team",
            "user",
            "role",
            "status",
            "organization_role",
            "invited_by",
            "joined_at",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "team",
            "user",
            "invited_by",
            "joined_at",
            "created_at",
        ]

    def get_organization_role(self, obj):
        """Get user's role in the organization."""
        try:
            org_membership = OrganizationMembership.objects.get(
                organization=obj.team.organization, user=obj.user, status="active"
            )
            return org_membership.role
        except OrganizationMembership.DoesNotExist:
            return None


class TeamInviteSerializer(serializers.Serializer):
    """Serializer for inviting users to team."""

    email = serializers.EmailField()
    role = serializers.ChoiceField(choices=TeamMembership.ROLES, default="viewer")

    def validate_email(self, value):
        """Validate that user exists and is org member."""
        try:
            user = User.objects.get(email=value)
            self.user = user
            return value
        except User.DoesNotExist:
            raise serializers.ValidationError("User with this email does not exist.")

    def validate(self, attrs):
        """Check if user is org member and not already team member."""
        team = self.context["team"]

        # Check if user is organization member
        if not OrganizationMembership.objects.filter(
            organization=team.organization, user=self.user, status="active"
        ).exists():
            raise serializers.ValidationError(
                "User must be an organization member first."
            )

        # Check if already team member
        if TeamMembership.objects.filter(team=team, user=self.user).exists():
            raise serializers.ValidationError("User is already a member of this team.")

        return attrs

    def save(self):
        """Create the team membership."""
        team = self.context["team"]
        invited_by = self.context["request"].user

        membership = TeamMembership.objects.create(
            team=team,
            user=self.user,
            role=self.validated_data["role"],
            status="active",
            invited_by=invited_by,
        )

        return membership


class OrganizationStatsSerializer(serializers.Serializer):
    """Serializer for organization statistics."""

    member_count = serializers.IntegerField()
    team_count = serializers.IntegerField()
    document_count = serializers.IntegerField()
    storage_used_gb = serializers.FloatField()
    active_members_today = serializers.IntegerField()
    recent_activities = serializers.ListField()
