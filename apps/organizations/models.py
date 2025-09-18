"""
Organization models for Smart Collaborative Backend.

This module defines the organizational structure:
- Organizations (top-level entities like companies)
- Teams (within organizations, like departments)
- Memberships (user roles in organizations and teams)
"""
import uuid
from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError


class Organization(models.Model):
    """
    Top-level organizational entity (company, enterprise, etc.).
    Contains teams and manages overall settings and subscriptions.
    """
    
    SUBSCRIPTION_PLANS = [
        ('free', 'Free'),
        ('pro', 'Pro'),
        ('enterprise', 'Enterprise'),
    ]
    
    SUBSCRIPTION_STATUS = [
        ('active', 'Active'),
        ('trial', 'Trial'),
        ('expired', 'Expired'),
        ('suspended', 'Suspended'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=100, unique=True)
    domain = models.CharField(
        max_length=255, 
        blank=True, 
        null=True,
        help_text="Email domain for auto-join (e.g., 'company.com')"
    )
    description = models.TextField(blank=True)
    logo_url = models.URLField(max_length=500, blank=True, null=True)
    
    # Settings stored as JSON
    settings = models.JSONField(
        default=dict,
        blank=True,
        help_text="Organization-specific settings and preferences"
    )
    
    # Subscription management
    subscription_plan = models.CharField(
        max_length=50, 
        choices=SUBSCRIPTION_PLANS, 
        default='free'
    )
    subscription_status = models.CharField(
        max_length=20, 
        choices=SUBSCRIPTION_STATUS, 
        default='active'
    )
    max_members = models.PositiveIntegerField(default=10)
    max_documents = models.PositiveIntegerField(default=100)
    max_storage_gb = models.PositiveIntegerField(default=5)
    
    # Ownership and timestamps
    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='created_organizations'
    )
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'organizations'
        ordering = ['name']
        indexes = [
            models.Index(fields=['slug'], name='idx_org_slug'),
            models.Index(fields=['domain'], name='idx_org_domain'),
            models.Index(fields=['created_by'], name='idx_org_created_by'),
            models.Index(fields=['subscription_plan', 'subscription_status'], name='idx_org_subscription'),
            models.Index(fields=['-created_at'], name='idx_org_created_at'),
        ]
    
    def __str__(self):
        return self.name
    
    def clean(self):
        """Validate organization data."""
        if self.domain and '@' in self.domain:
            raise ValidationError("Domain should not include '@' symbol")
    
    @property
    def member_count(self):
        """Get current number of organization members."""
        return self.memberships.filter(status='active').count()
    
    @property
    def team_count(self):
        """Get number of teams in this organization."""
        return self.teams.count()
    
    @property
    def is_at_member_limit(self):
        """Check if organization has reached member limit."""
        return self.member_count >= self.max_members
    
    def can_add_member(self):
        """Check if organization can add more members."""
        return not self.is_at_member_limit
    
    def get_default_team(self):
        """Get or create the default team for this organization."""
        default_team, created = self.teams.get_or_create(
            is_default=True,
            defaults={
                'name': f'{self.name} Team',
                'slug': 'default',
                'description': f'Default team for {self.name}',
                'created_by': self.created_by,
            }
        )
        return default_team


class Team(models.Model):
    """
    Teams within organizations (departments, projects, etc.).
    Teams contain users and documents.
    """
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='teams'
    )
    name = models.CharField(max_length=255)
    slug = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    color = models.CharField(
        max_length=7, 
        default='#3B82F6',
        help_text="Hex color code for UI display"
    )
    
    # Settings stored as JSON
    settings = models.JSONField(
        default=dict,
        blank=True,
        help_text="Team-specific settings and preferences"
    )
    
    # Special flags
    is_default = models.BooleanField(
        default=False,
        help_text="Default team for new organization members"
    )
    is_archived = models.BooleanField(default=False)
    
    # Ownership and timestamps
    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='created_teams'
    )
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'teams'
        ordering = ['organization', 'name']
        unique_together = [['organization', 'slug']]
        indexes = [
            models.Index(fields=['organization'], name='idx_team_organization'),
            models.Index(fields=['organization', 'slug'], name='idx_team_org_slug'),
            models.Index(fields=['created_by'], name='idx_team_created_by'),
            models.Index(fields=['organization', 'is_default'], name='idx_team_is_default'),
            models.Index(fields=['organization', 'is_archived'], name='idx_team_is_archived'),
            models.Index(fields=['-created_at'], name='idx_team_created_at'),
        ]
    
    def __str__(self):
        return f"{self.organization.name} / {self.name}"
    
    def clean(self):
        """Validate team data."""
        # Ensure only one default team per organization
        if self.is_default:
            existing_default = Team.objects.filter(
                organization=self.organization,
                is_default=True
            ).exclude(pk=self.pk)
            
            if existing_default.exists():
                raise ValidationError("Organization can only have one default team")
    
    @property
    def member_count(self):
        """Get current number of team members."""
        return self.memberships.filter(status='active').count()
    
    @property
    def document_count(self):
        """Get number of documents in this team."""
        # This will be implemented when documents app is ready
        return 0
    
    def get_user_role(self, user):
        """Get user's role in this team."""
        try:
            membership = self.memberships.get(user=user, status='active')
            return membership.role
        except TeamMembership.DoesNotExist:
            return None
    
    def add_member(self, user, role='viewer', invited_by=None):
        """Add a user to this team."""
        membership, created = TeamMembership.objects.get_or_create(
            team=self,
            user=user,
            defaults={
                'role': role,
                'invited_by': invited_by,
            }
        )
        return membership, created


class OrganizationMembership(models.Model):
    """
    User membership in an organization with roles and status.
    """
    
    ROLES = [
        ('owner', 'Owner'),
        ('admin', 'Admin'),
        ('member', 'Member'),
    ]
    
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('invited', 'Invited'),
        ('suspended', 'Suspended'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='memberships'
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='organization_memberships'
    )
    role = models.CharField(max_length=20, choices=ROLES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    
    # Invitation tracking
    invited_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sent_org_invitations'
    )
    invited_at = models.DateTimeField(null=True, blank=True)
    joined_at = models.DateTimeField(default=timezone.now)
    last_accessed = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(default=timezone.now)
    
    class Meta:
        db_table = 'organization_memberships'
        unique_together = [['organization', 'user']]
        ordering = ['organization', 'role', 'user__username']
        indexes = [
            models.Index(fields=['organization', 'user'], name='idx_org_mem_org_user'),
            models.Index(fields=['user'], name='idx_org_mem_user'),
            models.Index(fields=['organization', 'role'], name='idx_org_mem_role'),
            models.Index(fields=['organization', 'status'], name='idx_org_mem_status'),
            models.Index(fields=['-last_accessed'], name='idx_org_mem_last_accessed'),
            models.Index(fields=['-created_at'], name='idx_org_mem_created_at'),
        ]
    
    def __str__(self):
        return f"{self.user.username} - {self.organization.name} ({self.role})"
    
    def update_last_accessed(self):
        """Update the last accessed timestamp."""
        self.last_accessed = timezone.now()
        self.save(update_fields=['last_accessed'])
    
    @property
    def is_admin_or_owner(self):
        """Check if user has admin privileges."""
        return self.role in ['admin', 'owner']
    
    @property
    def can_manage_members(self):
        """Check if user can manage organization members."""
        return self.role in ['admin', 'owner'] and self.status == 'active'
    
    @property
    def can_manage_teams(self):
        """Check if user can manage teams."""
        return self.role in ['admin', 'owner'] and self.status == 'active'


class TeamMembership(models.Model):
    """
    User membership in a team with specific roles.
    """
    
    ROLES = [
        ('lead', 'Team Lead'),
        ('editor', 'Editor'),
        ('viewer', 'Viewer'),
    ]
    
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('invited', 'Invited'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    team = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name='memberships'
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='team_memberships'
    )
    role = models.CharField(max_length=20, choices=ROLES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    
    # Invitation tracking
    invited_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sent_team_invitations'
    )
    joined_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(default=timezone.now)
    
    class Meta:
        db_table = 'team_memberships'
        unique_together = [['team', 'user']]
        ordering = ['team', 'role', 'user__username']
        indexes = [
            models.Index(fields=['team', 'user'], name='idx_team_mem_team_user'),
            models.Index(fields=['user'], name='idx_team_mem_user'),
            models.Index(fields=['team', 'role'], name='idx_team_mem_role'),
            models.Index(fields=['team', 'status'], name='idx_team_mem_status'),
            models.Index(fields=['-created_at'], name='idx_team_mem_created_at'),
        ]
    
    def __str__(self):
        return f"{self.user.username} - {self.team.name} ({self.role})"
    
    def clean(self):
        """Validate team membership."""
        # Ensure user is a member of the organization
        if not OrganizationMembership.objects.filter(
            organization=self.team.organization,
            user=self.user,
            status='active'
        ).exists():
            raise ValidationError("User must be a member of the organization first")
    
    @property
    def can_edit_documents(self):
        """Check if user can edit documents in this team."""
        return self.role in ['lead', 'editor'] and self.status == 'active'
    
    @property
    def can_manage_team(self):
        """Check if user can manage team settings and members."""
        return self.role == 'lead' and self.status == 'active'
    
    @property
    def organization_membership(self):
        """Get the user's organization membership."""
        try:
            return OrganizationMembership.objects.get(
                organization=self.team.organization,
                user=self.user,
                status='active'
            )
        except OrganizationMembership.DoesNotExist:
            return None


# Signal handlers to maintain data consistency
from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender=Organization)
def create_owner_membership(sender, instance, created, **kwargs):
    """Create owner membership for organization creator."""
    if created:
        OrganizationMembership.objects.get_or_create(
            organization=instance,
            user=instance.created_by,
            defaults={
                'role': 'owner',
                'status': 'active',
            }
        )


@receiver(post_save, sender=Organization)
def create_default_team(sender, instance, created, **kwargs):
    """Create a default team when an organization is created."""
    if created:
        Team.objects.create(
            organization=instance,
            name=f'{instance.name} Team',
            slug='default',
            description=f'Default team for {instance.name}',
            is_default=True,
            created_by=instance.created_by,
        )


@receiver(post_save, sender=OrganizationMembership)
def add_to_default_team(sender, instance, created, **kwargs):
    """Add new organization members to the default team."""
    if created and instance.status == 'active':
        default_team = instance.organization.get_default_team()
        TeamMembership.objects.get_or_create(
            team=default_team,
            user=instance.user,
            defaults={
                'role': 'viewer',
                'status': 'active',
            }
        )
