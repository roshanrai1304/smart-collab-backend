"""
Django admin configuration for organizations app.
"""

from django.contrib import admin
from django.utils.html import format_html

from .models import Organization, OrganizationMembership, Team, TeamMembership


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    """Admin interface for Organization model."""

    list_display = [
        "name",
        "slug",
        "subscription_plan",
        "subscription_status",
        "member_count",
        "team_count",
        "created_by",
        "created_at",
    ]
    list_filter = ["subscription_plan", "subscription_status", "created_at"]
    search_fields = ["name", "slug", "domain"]
    readonly_fields = ["id", "created_at", "updated_at", "member_count", "team_count"]
    prepopulated_fields = {"slug": ("name",)}

    fieldsets = (
        (
            "Basic Information",
            {"fields": ("name", "slug", "description", "logo_url", "domain")},
        ),
        (
            "Subscription",
            {
                "fields": (
                    "subscription_plan",
                    "subscription_status",
                    "max_members",
                    "max_documents",
                    "max_storage_gb",
                )
            },
        ),
        ("Settings", {"fields": ("settings",), "classes": ("collapse",)}),
        (
            "Metadata",
            {
                "fields": (
                    "id",
                    "created_by",
                    "created_at",
                    "updated_at",
                    "member_count",
                    "team_count",
                ),
                "classes": ("collapse",),
            },
        ),
    )

    def member_count(self, obj):
        """Display member count."""
        return obj.member_count

    member_count.short_description = "Members"

    def team_count(self, obj):
        """Display team count."""
        return obj.team_count

    team_count.short_description = "Teams"


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    """Admin interface for Team model."""

    list_display = [
        "name",
        "organization",
        "slug",
        "member_count",
        "is_default",
        "is_archived",
        "created_by",
        "created_at",
    ]
    list_filter = ["organization", "is_default", "is_archived", "created_at"]
    search_fields = ["name", "slug", "description", "organization__name"]
    readonly_fields = ["id", "created_at", "updated_at", "member_count"]

    fieldsets = (
        (
            "Basic Information",
            {"fields": ("organization", "name", "slug", "description", "color")},
        ),
        ("Flags", {"fields": ("is_default", "is_archived")}),
        ("Settings", {"fields": ("settings",), "classes": ("collapse",)}),
        (
            "Metadata",
            {
                "fields": (
                    "id",
                    "created_by",
                    "created_at",
                    "updated_at",
                    "member_count",
                ),
                "classes": ("collapse",),
            },
        ),
    )

    def member_count(self, obj):
        """Display member count."""
        return obj.member_count

    member_count.short_description = "Members"

    def color_display(self, obj):
        """Display color as a colored box."""
        return format_html(
            '<div style="width: 20px; height: 20px; background-color: {}; border: 1px solid #ccc;"></div>',
            obj.color,
        )

    color_display.short_description = "Color"


@admin.register(OrganizationMembership)
class OrganizationMembershipAdmin(admin.ModelAdmin):
    """Admin interface for OrganizationMembership model."""

    list_display = [
        "user",
        "organization",
        "role",
        "status",
        "joined_at",
        "last_accessed",
        "invited_by",
    ]
    list_filter = ["role", "status", "organization", "joined_at"]
    search_fields = [
        "user__username",
        "user__email",
        "user__first_name",
        "user__last_name",
        "organization__name",
    ]
    readonly_fields = ["id", "created_at", "last_accessed"]

    fieldsets = (
        ("Membership", {"fields": ("organization", "user", "role", "status")}),
        ("Invitation Details", {"fields": ("invited_by", "invited_at", "joined_at")}),
        (
            "Metadata",
            {"fields": ("id", "created_at", "last_accessed"), "classes": ("collapse",)},
        ),
    )

    def get_queryset(self, request):
        """Optimize queryset with select_related."""
        return (
            super()
            .get_queryset(request)
            .select_related("user", "organization", "invited_by")
        )


@admin.register(TeamMembership)
class TeamMembershipAdmin(admin.ModelAdmin):
    """Admin interface for TeamMembership model."""

    list_display = ["user", "team", "role", "status", "joined_at", "invited_by"]
    list_filter = ["role", "status", "team__organization", "team", "joined_at"]
    search_fields = [
        "user__username",
        "user__email",
        "user__first_name",
        "user__last_name",
        "team__name",
        "team__organization__name",
    ]
    readonly_fields = ["id", "created_at"]

    fieldsets = (
        ("Membership", {"fields": ("team", "user", "role", "status")}),
        ("Invitation Details", {"fields": ("invited_by", "joined_at")}),
        ("Metadata", {"fields": ("id", "created_at"), "classes": ("collapse",)}),
    )

    def get_queryset(self, request):
        """Optimize queryset with select_related."""
        return (
            super()
            .get_queryset(request)
            .select_related("user", "team", "team__organization", "invited_by")
        )
