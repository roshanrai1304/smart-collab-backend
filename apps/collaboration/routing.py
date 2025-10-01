"""
WebSocket routing for collaboration app.
"""

from django.urls import path

from .consumers import CollaborationConsumer

websocket_urlpatterns = [
    path("ws/collaboration/<uuid:room_id>/", CollaborationConsumer.as_asgi()),
]
