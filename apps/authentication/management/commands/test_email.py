"""
Django management command to test email functionality.
"""
from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from django.conf import settings
from apps.authentication.utils import send_verification_email, send_password_reset_email


class Command(BaseCommand):
    help = 'Test email functionality'

    def add_arguments(self, parser):
        parser.add_argument(
            '--email',
            type=str,
            required=True,
            help='Email address to send test emails to'
        )
        parser.add_argument(
            '--type',
            type=str,
            choices=['basic', 'verification', 'reset', 'all'],
            default='basic',
            help='Type of email to send'
        )

    def handle(self, *args, **options):
        email = options['email']
        email_type = options['type']

        self.stdout.write(f"Testing email functionality...")
        self.stdout.write(f"Email backend: {settings.EMAIL_BACKEND}")
        self.stdout.write(f"From email: {settings.DEFAULT_FROM_EMAIL}")
        self.stdout.write(f"Target email: {email}")
        self.stdout.write("-" * 50)

        try:
            if email_type in ['basic', 'all']:
                self.test_basic_email(email)
            
            if email_type in ['verification', 'all']:
                self.test_verification_email(email)
            
            if email_type in ['reset', 'all']:
                self.test_reset_email(email)

            self.stdout.write(
                self.style.SUCCESS('✅ All email tests completed successfully!')
            )

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Email test failed: {str(e)}')
            )

    def test_basic_email(self, email):
        """Test basic email sending."""
        self.stdout.write("📧 Testing basic email...")
        
        send_mail(
            subject='Test Email from Smart Collab',
            message='This is a test email to verify email configuration.',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            fail_silently=False,
        )
        
        self.stdout.write(self.style.SUCCESS('✅ Basic email sent'))

    def test_verification_email(self, email):
        """Test verification email."""
        self.stdout.write("📧 Testing verification email...")
        
        test_token = 'test-verification-token-123'
        send_verification_email(email, test_token)
        
        self.stdout.write(self.style.SUCCESS('✅ Verification email sent'))

    def test_reset_email(self, email):
        """Test password reset email."""
        self.stdout.write("📧 Testing password reset email...")
        
        test_token = 'test-reset-token-456'
        send_password_reset_email(email, test_token)
        
        self.stdout.write(self.style.SUCCESS('✅ Password reset email sent'))
