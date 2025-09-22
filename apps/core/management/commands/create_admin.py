"""
Simple management command to create an admin user quickly.

Usage:
    python manage.py create_admin
    python manage.py create_admin --username admin --email admin@example.com
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.authentication.models import UserProfile

User = get_user_model()


class Command(BaseCommand):
    help = "Create an admin user quickly"

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            type=str,
            default="admin",
            help="Username for the admin user (default: admin)",
        )
        parser.add_argument(
            "--email",
            type=str,
            default="admin@smartcollab.com",
            help="Email for the admin user (default: admin@smartcollab.com)",
        )
        parser.add_argument(
            "--password",
            type=str,
            default="admin123",
            help="Password for the admin user (default: admin123)",
        )

    def handle(self, *args, **options):
        username = options["username"]
        email = options["email"]
        password = options["password"]

        self.stdout.write(f"Creating admin user: {username}")

        try:
            with transaction.atomic():
                if User.objects.filter(username=username).exists():
                    self.stdout.write(
                        self.style.WARNING(f'User "{username}" already exists!')
                    )
                    return

                # Create superuser
                user = User.objects.create_superuser(
                    username=username,
                    email=email,
                    password=password,
                    first_name="Admin",
                    last_name="User",
                )

                # Create UserProfile
                UserProfile.objects.create(
                    user=user,
                    bio="System Administrator",
                    phone_number="",
                    user_timezone="UTC",
                    language="en",
                    theme="light",
                    email_notifications=True,
                    push_notifications=True,
                    preferences={
                        "dashboard_layout": "grid",
                        "auto_save": True,
                        "collaboration_sounds": True,
                    },
                )

                self.stdout.write(
                    self.style.SUCCESS(
                        f'✅ Admin user "{username}" created successfully!'
                    )
                )
                self.stdout.write(f"Login credentials: {username} / {password}")
                self.stdout.write("Access admin panel at: http://127.0.0.1:8000/admin/")

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"❌ Error creating admin user: {str(e)}")
            )
