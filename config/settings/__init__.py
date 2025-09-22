"""
Django settings module selector.
"""

import os

# Determine which settings to use based on environment
ENVIRONMENT = os.getenv("DJANGO_ENVIRONMENT", "development")

if ENVIRONMENT == "production":
    from .production import *  # noqa: F401, F403
elif ENVIRONMENT == "testing":
    from .testing import *  # noqa: F401, F403
else:
    from .development import *  # noqa: F401, F403
