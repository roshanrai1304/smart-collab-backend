"""
URLs for documents app.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import DocumentViewSet

# Create router for documents
router = DefaultRouter()
router.register(r"", DocumentViewSet, basename="document")

urlpatterns = [
    # Document CRUD and management
    path("", include(router.urls)),
]
