"""
Development settings for Smart Collaborative Backend project.
"""

from .base import *  # noqa: F401, F403

# Development-specific settings
DEBUG = True
ALLOWED_HOSTS = ["*"]

# CORS settings for development
CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True

# Email backend for development (use .env setting)
# EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'  # Commented out to use .env setting

# Development logging
LOGGING["handlers"]["console"]["level"] = "DEBUG"  # noqa: F405
LOGGING["loggers"]["django"]["level"] = "DEBUG"  # noqa: F405

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
