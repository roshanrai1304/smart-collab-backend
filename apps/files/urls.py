"""
URL configuration for files app.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import FileShareAccessView, FileShareDownloadView, FileUploadViewSet

# Create router and register viewsets
router = DefaultRouter()
router.register(r"", FileUploadViewSet, basename="files")

urlpatterns = [
    # File management endpoints
    path("", include(router.urls)),
    # Public file sharing endpoints
    path(
        "share/<str:share_token>/",
        FileShareAccessView.as_view(),
        name="file_share_access",
    ),
    path(
        "share/<str:share_token>/download/",
        FileShareDownloadView.as_view(),
        name="file_share_download",
    ),
]
