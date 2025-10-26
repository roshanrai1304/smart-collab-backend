"""
WebSocket consumers for AI services.

Handles real-time AI processing updates and streaming results.
"""

import json
import logging
from typing import Dict, Any

from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser

from apps.documents.models import Document

logger = logging.getLogger(__name__)


class AIDocumentConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for AI document processing updates.
    
    Provides real-time updates during AI processing.
    """
    
    async def connect(self):
        """Handle WebSocket connection."""
        self.document_id = self.scope['url_route']['kwargs']['document_id']
        self.group_name = f"ai_document_{self.document_id}"
        
        # Check authentication
        user = self.scope.get('user', AnonymousUser())
        if user.is_anonymous:
            # Try to get user from token in query params
            token = self.scope.get('query_string', b'').decode()
            if 'token=' in token:
                token_value = token.split('token=')[1].split('&')[0]
                user = await self.get_user_from_token(token_value)
                if not user:
                    await self.close(code=4001)  # Unauthorized
                    return
            else:
                await self.close(code=4001)  # Unauthorized
                return
        
        # Check document access permissions
        has_access = await self.check_document_access(user, self.document_id)
        if not has_access:
            await self.close(code=4003)  # Forbidden
            return
        
        # Join document group
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )
        
        await self.accept()
        logger.info(f"AI WebSocket connected for document {self.document_id}")
    
    async def disconnect(self, close_code):
        """Handle WebSocket disconnection."""
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name
            )
        logger.info(f"AI WebSocket disconnected for document {self.document_id}")
    
    async def receive(self, text_data):
        """Handle incoming WebSocket messages."""
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            if message_type == 'get_status':
                # Send current processing status
                await self.send_processing_status()
            else:
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'message': f'Unknown message type: {message_type}'
                }))
                
        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Invalid JSON format'
            }))
        except Exception as e:
            logger.error(f"Error handling WebSocket message: {str(e)}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Internal server error'
            }))
    
    async def ai_processing_update(self, event):
        """Handle AI processing update events from the group."""
        await self.send(text_data=json.dumps({
            'type': 'ai_processing_update',
            'data': event['data']
        }))
    
    async def send_processing_status(self):
        """Send current processing status."""
        try:
            # Get AI metadata for the document
            metadata = await self.get_ai_metadata(self.document_id)
            
            await self.send(text_data=json.dumps({
                'type': 'processing_status',
                'status': {
                    'processing_status': metadata.get('processing_status') if metadata else 'pending',
                    'summary': metadata.get('summary') if metadata else None,
                    'last_processed': metadata.get('last_processed') if metadata else None,
                },
                'document_id': str(self.document_id)
            }))
            
        except Exception as e:
            logger.error(f"Error getting processing status: {str(e)}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Failed to get processing status'
            }))
    
    @database_sync_to_async
    def get_user_from_token(self, token: str):
        """Get user from JWT token."""
        try:
            from rest_framework_simplejwt.tokens import AccessToken
            from django.contrib.auth.models import User
            
            access_token = AccessToken(token)
            user_id = access_token['user_id']
            return User.objects.get(id=user_id)
        except Exception:
            return None
    
    @database_sync_to_async
    def check_document_access(self, user, document_id: str) -> bool:
        """Check if user has access to the document."""
        try:
            document = Document.objects.get(id=document_id)
            return document.can_read(user)
        except Document.DoesNotExist:
            return False
        except Exception:
            return False
    
    @database_sync_to_async
    def get_ai_metadata(self, document_id: str):
        """Get AI metadata for document."""
        try:
            from apps.ai_services.models import AIDocumentMetadata
            metadata = AIDocumentMetadata.objects.get(document_id=document_id)
            return {
                'processing_status': metadata.processing_status,
                'summary': metadata.summary,
                'last_processed': metadata.last_processed.isoformat() if metadata.last_processed else None,
            }
        except Exception:
            return None
