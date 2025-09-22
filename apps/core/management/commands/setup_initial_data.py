"""
Management command to set up initial data for the Smart Collab application.

This command creates:
- Superuser account
- Sample organizations and teams
- Sample users with different roles
- Initial documents and collaboration data

Usage:
    python manage.py setup_initial_data
    python manage.py setup_initial_data --minimal  # Only creates superuser
    python manage.py setup_initial_data --full     # Creates comprehensive sample data
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.authentication.models import UserProfile

User = get_user_model()


class Command(BaseCommand):
    help = "Set up initial data for Smart Collab application"

    def add_arguments(self, parser):
        parser.add_argument(
            "--minimal",
            action="store_true",
            help="Create only superuser and basic data",
        )
        parser.add_argument(
            "--full",
            action="store_true",
            help="Create comprehensive sample data",
        )
        parser.add_argument(
            "--superuser-username",
            type=str,
            default="admin",
            help="Username for the superuser (default: admin)",
        )
        parser.add_argument(
            "--superuser-email",
            type=str,
            default="admin@smartcollab.com",
            help="Email for the superuser (default: admin@smartcollab.com)",
        )
        parser.add_argument(
            "--superuser-password",
            type=str,
            default="admin123",
            help="Password for the superuser (default: admin123)",
        )

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS("🚀 Setting up initial data for Smart Collab...")
        )

        try:
            with transaction.atomic():
                # Always create superuser
                self.create_superuser(
                    username=options["superuser_username"],
                    email=options["superuser_email"],
                    password=options["superuser_password"],
                )

                if options["minimal"]:
                    self.stdout.write(self.style.SUCCESS("✅ Minimal setup completed!"))
                    return

                # Create sample users
                sample_users = self.create_sample_users()

                if options["full"]:
                    self.create_comprehensive_data(sample_users)
                    self.stdout.write(self.style.SUCCESS("✅ Full setup completed!"))
                else:
                    self.stdout.write(
                        self.style.SUCCESS("✅ Standard setup completed!")
                    )

                self.display_summary(options)

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Error during setup: {str(e)}"))
            raise CommandError(f"Setup failed: {str(e)}")

    def create_superuser(self, username, email, password):
        """Create superuser if it doesn't exist."""
        self.stdout.write("👤 Creating superuser...")

        if User.objects.filter(username=username).exists():
            self.stdout.write(
                self.style.WARNING(f'⚠️  Superuser "{username}" already exists')
            )
            return User.objects.get(username=username)

        superuser = User.objects.create_superuser(
            username=username,
            email=email,
            password=password,
            first_name="Super",
            last_name="Admin",
        )

        # Create UserProfile for superuser
        UserProfile.objects.get_or_create(
            user=superuser,
            defaults={
                "bio": "System Administrator",
                "phone_number": "+1234567890",
                "user_timezone": "UTC",
                "language": "en",
                "theme": "light",
                "email_notifications": True,
                "push_notifications": True,
                "preferences": {
                    "dashboard_layout": "grid",
                    "auto_save": True,
                    "collaboration_sounds": True,
                },
            },
        )

        self.stdout.write(self.style.SUCCESS(f'✅ Superuser "{username}" created'))
        return superuser

    def create_sample_users(self):
        """Create sample users with different roles."""
        self.stdout.write("👥 Creating sample users...")

        sample_users_data = [
            {
                "username": "john_doe",
                "email": "john.doe@example.com",
                "first_name": "John",
                "last_name": "Doe",
                "bio": "Product Manager with 5+ years experience",
                "phone_number": "+1234567891",
                "theme": "light",
            },
            {
                "username": "jane_smith",
                "email": "jane.smith@example.com",
                "first_name": "Jane",
                "last_name": "Smith",
                "bio": "Senior Developer and Team Lead",
                "phone_number": "+1234567892",
                "theme": "dark",
            },
            {
                "username": "mike_wilson",
                "email": "mike.wilson@example.com",
                "first_name": "Mike",
                "last_name": "Wilson",
                "bio": "UX Designer focused on user experience",
                "phone_number": "+1234567893",
                "theme": "auto",
            },
            {
                "username": "sarah_brown",
                "email": "sarah.brown@example.com",
                "first_name": "Sarah",
                "last_name": "Brown",
                "bio": "Marketing Specialist and Content Creator",
                "phone_number": "+1234567894",
                "theme": "light",
            },
        ]

        created_users = []

        for user_data in sample_users_data:
            username = user_data["username"]

            if User.objects.filter(username=username).exists():
                self.stdout.write(
                    self.style.WARNING(f'⚠️  User "{username}" already exists')
                )
                user = User.objects.get(username=username)
            else:
                user = User.objects.create_user(
                    username=username,
                    email=user_data["email"],
                    password="password123",  # Default password for sample users
                    first_name=user_data["first_name"],
                    last_name=user_data["last_name"],
                )

                # Create UserProfile
                UserProfile.objects.get_or_create(
                    user=user,
                    defaults={
                        "bio": user_data["bio"],
                        "phone_number": user_data["phone_number"],
                        "user_timezone": "UTC",
                        "language": "en",
                        "theme": user_data["theme"],
                        "email_notifications": True,
                        "push_notifications": True,
                        "preferences": {
                            "dashboard_layout": (
                                "list" if user_data["theme"] == "dark" else "grid"
                            ),
                            "auto_save": True,
                            "collaboration_sounds": True,
                        },
                    },
                )

                self.stdout.write(self.style.SUCCESS(f'✅ User "{username}" created'))

            created_users.append(user)

        return created_users

    def create_comprehensive_data(self, sample_users):
        """Create comprehensive sample data including organizations, teams, etc."""
        self.stdout.write("🏢 Creating comprehensive sample data...")

        # Note: This will be expanded when we create other apps (organizations, documents, etc.)
        # For now, we'll just create the user-related data

        self.stdout.write("📊 Creating sample user activities...")

        # Create some login attempts for demonstration
        import random
        from datetime import timedelta

        from django.utils import timezone

        from apps.authentication.models import LoginAttempt

        for user in sample_users[:2]:  # Create login attempts for first 2 users
            for i in range(random.randint(1, 3)):
                LoginAttempt.objects.create(
                    email=user.email,
                    ip_address=f"192.168.1.{random.randint(100, 200)}",
                    user_agent="Mozilla/5.0 (Test Browser)",
                    success=random.choice([True, False]),
                    device_info={
                        "device_type": random.choice(["desktop", "mobile", "tablet"]),
                        "os": random.choice(
                            ["Windows", "macOS", "Linux", "iOS", "Android"]
                        ),
                        "browser": random.choice(
                            ["Chrome", "Firefox", "Safari", "Edge"]
                        ),
                    },
                    created_at=timezone.now() - timedelta(days=random.randint(1, 30)),
                )

        self.stdout.write("✅ Comprehensive data created")

    def display_summary(self, options):
        """Display a summary of created data."""
        self.stdout.write("\n" + "=" * 50)
        self.stdout.write(self.style.SUCCESS("📋 SETUP SUMMARY"))
        self.stdout.write("=" * 50)

        # Count users
        total_users = User.objects.count()
        superusers = User.objects.filter(is_superuser=True).count()
        regular_users = total_users - superusers

        self.stdout.write(f"👥 Users created: {total_users}")
        self.stdout.write(f"   - Superusers: {superusers}")
        self.stdout.write(f"   - Regular users: {regular_users}")

        # Display login credentials
        self.stdout.write("\n🔐 LOGIN CREDENTIALS:")
        self.stdout.write(
            f'   Superuser: {options["superuser_username"]} / {options["superuser_password"]}'
        )

        if not options["minimal"]:
            self.stdout.write("   Sample users: username / password123")
            self.stdout.write("   - john_doe / password123")
            self.stdout.write("   - jane_smith / password123")
            self.stdout.write("   - mike_wilson / password123")
            self.stdout.write("   - sarah_brown / password123")

        self.stdout.write("\n🌐 ACCESS URLS:")
        self.stdout.write("   - Admin Panel: http://127.0.0.1:8000/admin/")
        self.stdout.write("   - API Root: http://127.0.0.1:8000/api/v1/")
        self.stdout.write(
            "   - API Docs: http://127.0.0.1:8000/api/v1/schema/swagger-ui/"
        )

        self.stdout.write("\n🚀 Next steps:")
        self.stdout.write("   1. Start the server: python manage.py runserver")
        self.stdout.write("   2. Visit the admin panel to manage users")
        self.stdout.write("   3. Test the API endpoints")

        self.stdout.write("\n" + "=" * 50)
