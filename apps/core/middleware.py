"""
Custom middleware for logging API requests and responses.
"""

import logging
import time

from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger("django.request")


class APILoggingMiddleware(MiddlewareMixin):
    """
    Middleware to log API requests and responses in a readable format.
    """

    def process_request(self, request):
        """Log incoming API requests."""
        # Store start time for response time calculation
        request._start_time = time.time()

        # Only log API requests (not static files, admin, etc.)
        if request.path.startswith("/api/"):
            # Get user info
            user_info = "Anonymous"
            if hasattr(request, "user") and request.user.is_authenticated:
                user_info = f"{request.user.username} (ID: {request.user.id})"

            # Log the request
            logger.info(
                f"📥 {request.method} {request.path} | User: {user_info} | "
                f"IP: {self.get_client_ip(request)}"
            )

            # Log request body for POST/PUT/PATCH (but limit size and exclude sensitive data)
            if request.method in ["POST", "PUT", "PATCH"] and hasattr(request, "body"):
                try:
                    body = request.body.decode("utf-8")
                    # Don't log passwords or tokens
                    if "password" not in body.lower() and "token" not in body.lower():
                        # Limit body size for logging
                        if len(body) > 500:
                            body = body[:500] + "... (truncated)"
                        logger.info(f"📝 Request Body: {body}")
                except (UnicodeDecodeError, AttributeError):
                    logger.info("📝 Request Body: [Binary or non-UTF8 content]")

    def process_response(self, request, response):
        """Log API responses."""
        # Only log API responses
        if request.path.startswith("/api/"):
            # Calculate response time
            response_time = 0
            if hasattr(request, "_start_time"):
                response_time = (
                    time.time() - request._start_time
                ) * 1000  # Convert to milliseconds

            # Get status emoji
            status_emoji = self.get_status_emoji(response.status_code)

            # Log the response
            logger.info(
                f"📤 {status_emoji} {response.status_code} {request.method} {request.path} | "
                f"Time: {response_time:.1f}ms | Size: {len(response.content)} bytes"
            )

            # Log response body for errors (4xx, 5xx) but limit size
            if response.status_code >= 400:
                try:
                    content = response.content.decode("utf-8")
                    if len(content) > 300:
                        content = content[:300] + "... (truncated)"
                    logger.info(f"❌ Error Response: {content}")
                except (UnicodeDecodeError, AttributeError):
                    logger.info("❌ Error Response: [Binary or non-UTF8 content]")

        return response

    def get_client_ip(self, request):
        """Get the client's IP address."""
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            ip = x_forwarded_for.split(",")[0]
        else:
            ip = request.META.get("REMOTE_ADDR")
        return ip

    def get_status_emoji(self, status_code):
        """Get emoji based on HTTP status code."""
        if 200 <= status_code < 300:
            return "✅"
        elif 300 <= status_code < 400:
            return "↩️"
        elif 400 <= status_code < 500:
            return "⚠️"
        elif status_code >= 500:
            return "🚨"
        else:
            return "❓"
