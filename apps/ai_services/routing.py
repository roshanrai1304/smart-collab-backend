"""
WebSocket routing for AI services app.
"""

from django.urls import path

from .consumers import AIDocumentConsumer

websocket_urlpatterns = [
    path("ws/ai/document/<uuid:document_id>/", AIDocumentConsumer.as_asgi()),
]
