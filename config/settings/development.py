"""
Development settings for Smart Collaborative Backend project.
"""

from datetime import timedelta

from .base import *  # noqa: F401, F403

# Development-specific settings
DEBUG = True
ALLOWED_HOSTS = ["*"]

# CORS settings for development
CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True

# Email backend for development (use .env setting)
# EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'  # Commented out to use .env setting

# Development logging - Enhanced API request logging
LOGGING["handlers"]["console"]["level"] = "INFO"  # noqa: F405
LOGGING["handlers"]["api_console"]["level"] = "INFO"  # noqa: F405
LOGGING["loggers"]["django"]["level"] = "INFO"  # noqa: F405
LOGGING["loggers"]["django.server"]["level"] = "INFO"  # noqa: F405
LOGGING["loggers"]["django.request"]["level"] = "INFO"  # noqa: F405
LOGGING["loggers"]["apps"]["level"] = "INFO"  # noqa: F405

# Add custom formatter for development
LOGGING["formatters"]["dev_api"] = {  # noqa: F405
    "format": "🚀 {asctime} | {levelname} | {name} | {message}",
    "style": "{",
    "datefmt": "%H:%M:%S",
}

# Update console handler to use development formatter
LOGGING["handlers"]["console"]["formatter"] = "dev_api"  # noqa: F405
LOGGING["handlers"]["api_console"]["formatter"] = "dev_api"  # noqa: F405

# Development-specific Django REST Framework settings
REST_FRAMEWORK.update(  # noqa: F405
    {
        "DEFAULT_RENDERER_CLASSES": [
            "rest_framework.renderers.JSONRenderer",
            "rest_framework.renderers.BrowsableAPIRenderer",
        ],
    }
)

# Celery settings for development
CELERY_TASK_ALWAYS_EAGER = False
CELERY_TASK_EAGER_PROPAGATES = True

# JWT settings for development - longer token lifetimes for convenience
SIMPLE_JWT.update(  # noqa: F405
    {
        "ACCESS_TOKEN_LIFETIME": timedelta(days=1),  # 24 hours for development
        "REFRESH_TOKEN_LIFETIME": timedelta(days=90),  # 90 days for development
    }
)
