"""
Management command to reset/clear application data.

Usage:
    python manage.py reset_data --confirm
"""

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.db import transaction
from apps.authentication.models import UserProfile, LoginAttempt, PasswordResetToken, EmailVerification, RefreshToken

User = get_user_model()


class Command(BaseCommand):
    help = 'Reset/clear all application data'

    def add_arguments(self, parser):
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Confirm that you want to delete all data',
        )
        parser.add_argument(
            '--keep-superuser',
            action='store_true',
            help='Keep superuser accounts when resetting',
        )

    def handle(self, *args, **options):
        if not options['confirm']:
            self.stdout.write(
                self.style.ERROR(
                    '⚠️  This command will delete ALL data from the database!\n'
                    'Use --confirm flag to proceed: python manage.py reset_data --confirm'
                )
            )
            return

        self.stdout.write(self.style.WARNING('🗑️  Resetting application data...'))
        
        try:
            with transaction.atomic():
                # Count data before deletion
                user_count = User.objects.count()
                profile_count = UserProfile.objects.count()
                login_attempt_count = LoginAttempt.objects.count()
                
                if options['keep_superuser']:
                    # Delete non-superuser data
                    regular_users = User.objects.filter(is_superuser=False)
                    regular_user_ids = list(regular_users.values_list('id', flat=True))
                    
                    UserProfile.objects.filter(user_id__in=regular_user_ids).delete()
                    regular_users.delete()
                    
                    # Clear other data
                    LoginAttempt.objects.all().delete()
                    PasswordResetToken.objects.all().delete()
                    EmailVerification.objects.all().delete()
                    RefreshToken.objects.all().delete()
                    
                    remaining_users = User.objects.count()
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'✅ Data reset completed!\n'
                            f'   - Deleted {user_count - remaining_users} regular users\n'
                            f'   - Kept {remaining_users} superuser(s)\n'
                            f'   - Cleared all authentication data'
                        )
                    )
                else:
                    # Delete all data
                    UserProfile.objects.all().delete()
                    LoginAttempt.objects.all().delete()
                    PasswordResetToken.objects.all().delete()
                    EmailVerification.objects.all().delete()
                    RefreshToken.objects.all().delete()
                    User.objects.all().delete()
                    
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'✅ All data deleted!\n'
                            f'   - Deleted {user_count} users\n'
                            f'   - Deleted {profile_count} profiles\n'
                            f'   - Deleted {login_attempt_count} login attempts\n'
                            f'   - Cleared all authentication data'
                        )
                    )
                    
                    self.stdout.write(
                        self.style.WARNING(
                            '\n💡 Run "python manage.py setup_initial_data" to recreate sample data'
                        )
                    )
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Error during reset: {str(e)}'))
            raise CommandError(f'Reset failed: {str(e)}')
