"""
URLs for authentication app.
"""
from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import (
    RegisterView,
    CustomTokenObtainPairView,
    ProfileView,
    PasswordChangeView,
    EmailVerificationView,
    ResendVerificationView,
    current_user
)

urlpatterns = [
    # Authentication endpoints
    path('register/', RegisterView.as_view(), name='auth_register'),
    path('login/', CustomTokenObtainPairView.as_view(), name='auth_login'),
    path('token/refresh/', TokenRefreshView.as_view(), name='auth_token_refresh'),
    
    # Email verification endpoints
    path('verify-email/', EmailVerificationView.as_view(), name='auth_verify_email'),
    path('resend-verification/', ResendVerificationView.as_view(), name='auth_resend_verification'),
    
    # User profile endpoints
    path('profile/', ProfileView.as_view(), name='auth_profile'),
    path('me/', current_user, name='auth_current_user'),
    
    # Password management
    path('password/change/', PasswordChangeView.as_view(), name='auth_password_change'),
]