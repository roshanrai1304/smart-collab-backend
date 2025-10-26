"""
URL configuration for collaboration app.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import CollaborationRoomViewSet, WebSocketTokenView

# Create router and register viewsets
router = DefaultRouter()
router.register(r"rooms", CollaborationRoomViewSet, basename="collaboration_rooms")

urlpatterns = [
    # Collaboration room management
    path("", include(router.urls)),
    # WebSocket authentication
    path("ws-token/", WebSocketTokenView.as_view(), name="collaboration_ws_token"),
]
