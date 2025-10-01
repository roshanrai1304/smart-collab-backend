"""
WebSocket consumers for real-time collaboration.
"""

import json
import logging

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.utils import timezone
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import UntypedToken

from .models import (
    CollaborationActivity,
    CollaborationRoom,
    CollaborationSession,
    CursorPosition,
)

logger = logging.getLogger(__name__)


class CollaborationConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for real-time collaboration.
    Handles document editing, cursor tracking, and presence.
    """

    async def connect(self):
        """Handle WebSocket connection."""
        # Extract room ID from URL
        self.room_id = self.scope["url_route"]["kwargs"]["room_id"]
        self.room_group_name = f"collaboration_{self.room_id}"

        # Initialize variables
        self.user = None
        self.session = None
        self.room = None

        # Accept connection first
        await self.accept()

        # Send connection established message
        await self.send(
            text_data=json.dumps(
                {
                    "type": "connection_established",
                    "message": "Connected to collaboration room",
                }
            )
        )

    async def disconnect(self, close_code):
        """Handle WebSocket disconnection."""
        # Leave room group
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

        # Update session status
        if self.session:
            await self.disconnect_session()

        # Broadcast user leave event
        if self.user and self.room:
            await self.broadcast_user_leave()

    async def receive(self, text_data):
        """Handle incoming WebSocket messages."""
        try:
            data = json.loads(text_data)
            message_type = data.get("type")

            # Handle authentication first
            if message_type == "authenticate":
                await self.handle_authentication(data)
            elif not self.user:
                await self.send_error("Authentication required")
                return

            # Handle different message types
            handlers = {
                "join_room": self.handle_join_room,
                "text_change": self.handle_text_change,
                "cursor_move": self.handle_cursor_move,
                "selection_change": self.handle_selection_change,
                "user_typing": self.handle_user_typing,
                "document_save": self.handle_document_save,
                "heartbeat": self.handle_heartbeat,
            }

            handler = handlers.get(message_type)
            if handler:
                await handler(data)
            else:
                await self.send_error(f"Unknown message type: {message_type}")

        except json.JSONDecodeError:
            await self.send_error("Invalid JSON format")
        except Exception as e:
            logger.error(f"Error handling message: {e}")
            await self.send_error("Internal server error")

    async def handle_authentication(self, data):
        """Handle user authentication."""
        try:
            token = data.get("token")
            if not token:
                await self.send_error("Token required")
                return

            # Verify JWT token
            try:
                UntypedToken(token)
            except (InvalidToken, TokenError):
                await self.send_error("Invalid token")
                return

            # Get user from token
            from rest_framework_simplejwt.authentication import JWTAuthentication

            jwt_auth = JWTAuthentication()
            validated_token = jwt_auth.get_validated_token(token)
            self.user = await database_sync_to_async(jwt_auth.get_user)(validated_token)

            if not self.user:
                await self.send_error("User not found")
                return

            # Get room
            self.room = await self.get_room()
            if not self.room:
                await self.send_error("Room not found")
                return

            # Check if user can join room
            can_join = await database_sync_to_async(self.room.can_join)(self.user)
            if not can_join:
                await self.send_error("Cannot join room")
                return

            # Send authentication success
            await self.send(
                text_data=json.dumps(
                    {
                        "type": "authenticated",
                        "user": {
                            "id": str(self.user.id),
                            "username": self.user.username,
                            "first_name": self.user.first_name,
                            "last_name": self.user.last_name,
                        },
                        "room": {
                            "id": str(self.room.id),
                            "name": self.room.name,
                            "document_id": str(self.room.document.id),
                        },
                    }
                )
            )

        except Exception as e:
            logger.error(f"Authentication error: {e}")
            await self.send_error("Authentication failed")

    async def handle_join_room(self, data):
        """Handle user joining room."""
        try:
            # Create or get session
            self.session = await self.get_or_create_session(data)

            # Join room group
            await self.channel_layer.group_add(self.room_group_name, self.channel_name)

            # Get active participants
            active_participants = await self.get_active_participants()

            # Send room joined confirmation
            await self.send(
                text_data=json.dumps(
                    {
                        "type": "room_joined",
                        "session_id": str(self.session.id),
                        "participants": active_participants,
                        "room_settings": {
                            "enable_cursor_tracking": self.room.enable_cursor_tracking,
                            "enable_voice": self.room.enable_voice,
                            "enable_video": self.room.enable_video,
                        },
                    }
                )
            )

            # Broadcast user join event
            await self.broadcast_user_join()

            # Record activity
            await self.record_activity(
                "user_join",
                {
                    "user_id": str(self.user.id),
                    "session_id": str(self.session.id),
                },
            )

        except Exception as e:
            logger.error(f"Error joining room: {e}")
            await self.send_error("Failed to join room")

    async def handle_text_change(self, data):
        """Handle document text changes."""
        try:
            # Validate required fields
            required_fields = ["operation", "position", "content"]
            if not all(field in data for field in required_fields):
                await self.send_error("Missing required fields for text change")
                return

            # Record activity
            activity = await self.record_activity(
                "text_insert",
                {
                    "operation": data["operation"],
                    "position": data["position"],
                    "content": data["content"],
                    "length": len(data["content"]),
                },
            )

            # Broadcast to other participants
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "text_change_broadcast",
                    "activity_id": str(activity.id),
                    "user_id": str(self.user.id),
                    "operation": data["operation"],
                    "position": data["position"],
                    "content": data["content"],
                    "timestamp": activity.server_timestamp.isoformat(),
                    "sender_channel": self.channel_name,
                },
            )

        except Exception as e:
            logger.error(f"Error handling text change: {e}")
            await self.send_error("Failed to process text change")

    async def handle_cursor_move(self, data):
        """Handle cursor position updates."""
        try:
            position_data = data.get("position", {})

            # Update cursor position
            await self.update_cursor_position(position_data)

            # Broadcast to other participants (if cursor tracking enabled)
            if self.room.enable_cursor_tracking:
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        "type": "cursor_move_broadcast",
                        "user_id": str(self.user.id),
                        "position": position_data,
                        "sender_channel": self.channel_name,
                    },
                )

        except Exception as e:
            logger.error(f"Error handling cursor move: {e}")

    async def handle_selection_change(self, data):
        """Handle text selection changes."""
        try:
            selection_data = data.get("selection", {})

            # Update cursor position with selection
            await self.update_cursor_position(data.get("position", {}), selection_data)

            # Broadcast selection change
            if self.room.enable_cursor_tracking:
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        "type": "selection_change_broadcast",
                        "user_id": str(self.user.id),
                        "selection": selection_data,
                        "sender_channel": self.channel_name,
                    },
                )

        except Exception as e:
            logger.error(f"Error handling selection change: {e}")

    async def handle_user_typing(self, data):
        """Handle user typing indicators."""
        try:
            is_typing = data.get("is_typing", False)

            # Broadcast typing status
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "user_typing_broadcast",
                    "user_id": str(self.user.id),
                    "is_typing": is_typing,
                    "sender_channel": self.channel_name,
                },
            )

        except Exception as e:
            logger.error(f"Error handling typing indicator: {e}")

    async def handle_document_save(self, data):
        """Handle document save events."""
        try:
            # Record save activity
            await self.record_activity(
                "document_save",
                {
                    "document_version": data.get("version"),
                    "auto_save": data.get("auto_save", False),
                },
            )

            # Broadcast save event
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "document_save_broadcast",
                    "user_id": str(self.user.id),
                    "version": data.get("version"),
                    "sender_channel": self.channel_name,
                },
            )

        except Exception as e:
            logger.error(f"Error handling document save: {e}")

    async def handle_heartbeat(self, data):
        """Handle heartbeat/ping messages."""
        try:
            # Update session activity
            if self.session:
                await self.update_session_activity()

            # Send pong response
            await self.send(
                text_data=json.dumps(
                    {
                        "type": "pong",
                        "timestamp": timezone.now().isoformat(),
                    }
                )
            )

        except Exception as e:
            logger.error(f"Error handling heartbeat: {e}")

    # Broadcast message handlers
    async def text_change_broadcast(self, event):
        """Broadcast text changes to participants."""
        # Don't send to the sender
        if event["sender_channel"] == self.channel_name:
            return

        await self.send(
            text_data=json.dumps(
                {
                    "type": "text_change",
                    "activity_id": event["activity_id"],
                    "user_id": event["user_id"],
                    "operation": event["operation"],
                    "position": event["position"],
                    "content": event["content"],
                    "timestamp": event["timestamp"],
                }
            )
        )

    async def cursor_move_broadcast(self, event):
        """Broadcast cursor movements to participants."""
        # Don't send to the sender
        if event["sender_channel"] == self.channel_name:
            return

        await self.send(
            text_data=json.dumps(
                {
                    "type": "cursor_move",
                    "user_id": event["user_id"],
                    "position": event["position"],
                }
            )
        )

    async def selection_change_broadcast(self, event):
        """Broadcast selection changes to participants."""
        # Don't send to the sender
        if event["sender_channel"] == self.channel_name:
            return

        await self.send(
            text_data=json.dumps(
                {
                    "type": "selection_change",
                    "user_id": event["user_id"],
                    "selection": event["selection"],
                }
            )
        )

    async def user_typing_broadcast(self, event):
        """Broadcast typing indicators to participants."""
        # Don't send to the sender
        if event["sender_channel"] == self.channel_name:
            return

        await self.send(
            text_data=json.dumps(
                {
                    "type": "user_typing",
                    "user_id": event["user_id"],
                    "is_typing": event["is_typing"],
                }
            )
        )

    async def document_save_broadcast(self, event):
        """Broadcast document save events to participants."""
        # Don't send to the sender
        if event["sender_channel"] == self.channel_name:
            return

        await self.send(
            text_data=json.dumps(
                {
                    "type": "document_save",
                    "user_id": event["user_id"],
                    "version": event["version"],
                }
            )
        )

    async def user_join_broadcast(self, event):
        """Broadcast user join events to participants."""
        await self.send(
            text_data=json.dumps(
                {
                    "type": "user_join",
                    "user": event["user"],
                }
            )
        )

    async def user_leave_broadcast(self, event):
        """Broadcast user leave events to participants."""
        await self.send(
            text_data=json.dumps(
                {
                    "type": "user_leave",
                    "user": event["user"],
                }
            )
        )

    # Helper methods
    async def send_error(self, message):
        """Send error message to client."""
        await self.send(
            text_data=json.dumps(
                {
                    "type": "error",
                    "message": message,
                }
            )
        )

    @database_sync_to_async
    def get_room(self):
        """Get collaboration room."""
        try:
            return CollaborationRoom.objects.select_related("document", "team").get(
                id=self.room_id
            )
        except CollaborationRoom.DoesNotExist:
            return None

    @database_sync_to_async
    def get_or_create_session(self, data):
        """Get or create collaboration session."""
        session, created = CollaborationSession.objects.get_or_create(
            room=self.room,
            user=self.user,
            defaults={
                "connection_id": self.channel_name,
                "ip_address": self.scope.get("client", ["", None])[0],
                "user_agent": data.get("user_agent", ""),
                "client_info": data.get("client_info", {}),
            },
        )

        if not created:
            # Update existing session
            session.status = "active"
            session.connection_id = self.channel_name
            session.last_seen = timezone.now()
            session.save()

        return session

    @database_sync_to_async
    def get_active_participants(self):
        """Get list of active participants."""
        participants = []
        active_sessions = self.room.get_active_sessions()

        for session in active_sessions:
            participants.append(
                {
                    "id": str(session.user.id),
                    "username": session.user.username,
                    "first_name": session.user.first_name,
                    "last_name": session.user.last_name,
                    "role": session.user_role,
                    "joined_at": session.joined_at.isoformat(),
                }
            )

        return participants

    @database_sync_to_async
    def record_activity(self, activity_type, activity_data):
        """Record collaboration activity."""
        return CollaborationActivity.objects.create(
            room=self.room,
            session=self.session,
            user=self.user,
            activity_type=activity_type,
            activity_data=activity_data,
            client_timestamp=timezone.now(),
            document_version=1,  # TODO: Get actual document version
        )

    @database_sync_to_async
    def update_cursor_position(self, position_data, selection_data=None):
        """Update user cursor position."""
        cursor, created = CursorPosition.objects.get_or_create(
            room=self.room,
            user=self.user,
            defaults={
                "session": self.session,
                "position": position_data,
                "selection": selection_data,
            },
        )

        if not created:
            cursor.position = position_data
            if selection_data:
                cursor.selection = selection_data
            cursor.save()

        return cursor

    @database_sync_to_async
    def update_session_activity(self):
        """Update session last seen timestamp."""
        if self.session:
            self.session.update_activity()

    @database_sync_to_async
    def disconnect_session(self):
        """Mark session as disconnected."""
        self.session.disconnect()

    async def broadcast_user_join(self):
        """Broadcast user join event."""
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "user_join_broadcast",
                "user": {
                    "id": str(self.user.id),
                    "username": self.user.username,
                    "first_name": self.user.first_name,
                    "last_name": self.user.last_name,
                },
            },
        )

    async def broadcast_user_leave(self):
        """Broadcast user leave event."""
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "user_leave_broadcast",
                "user": {
                    "id": str(self.user.id),
                    "username": self.user.username,
                    "first_name": self.user.first_name,
                    "last_name": self.user.last_name,
                },
            },
        )
