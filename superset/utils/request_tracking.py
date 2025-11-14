# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

"""
Request tracking middleware for Flask.

This middleware adds request correlation IDs to help track logs across a single HTTP request.
"""
import uuid
from typing import Callable

import flask


class RequestTrackingMiddleware:
    """Middleware to add request IDs for log correlation."""
    
    def __init__(self, app: flask.Flask) -> None:
        """Initialize the middleware."""
        self.app = app
        self._register_hooks()
    
    def _register_hooks(self) -> None:
        """Register before_request and after_request hooks."""
        
        @self.app.before_request
        def set_request_start_time() -> None:
            """Record request start time for duration calculation."""
            import time
            flask.g.request_start_time = time.time()
        
        @self.app.before_request
        def assign_request_id() -> None:
            """Assign a unique ID to each request."""
            # Check if there's already a request ID in headers (for distributed tracing)
            request_id = flask.request.headers.get("X-Request-ID")
            
            if not request_id:
                # Generate a new UUID for this request
                request_id = str(uuid.uuid4())
            
            # Store in Flask's g object for access throughout the request
            flask.g.request_id = request_id
        
        # Removed log_request_start - we only log at the end to avoid duplicate logs
        
        @self.app.after_request
        def add_request_id_header(response: flask.Response) -> flask.Response:
            """Add request ID to response headers."""
            response.headers["X-Request-ID"] = flask.g.request_id
            return response
        
        @self.app.after_request
        def log_request_end(response: flask.Response) -> flask.Response:
            """Log HTTP access in structured format (replaces Gunicorn access logs)."""
            import logging
            import os
            import time
            
            # Optional: Filter out static asset requests to reduce log noise
            # Set LOG_STATIC_ASSETS=false to disable static asset logging
            log_static_assets = os.environ.get("LOG_STATIC_ASSETS", "true").lower() == "true"
            
            if not log_static_assets:
                # Skip logging for static assets (JS, CSS, images, fonts, etc.)
                path = flask.request.path.lower()
                if any(path.startswith(prefix) for prefix in [
                    "/static/",
                    "/api/v1/assets/",
                ]) or any(path.endswith(ext) for ext in [
                    ".js", ".css", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico",
                    ".woff", ".woff2", ".ttf", ".eot", ".map"
                ]):
                    return response
            
            # Calculate request duration if start time is available
            duration_ms = None
            duration_seconds = None
            if hasattr(flask.g, "request_start_time"):
                duration_seconds = time.time() - flask.g.request_start_time
                duration_ms = int(duration_seconds * 1000)
            
            # Get response size
            response_size = response.content_length
            if response_size is None:
                try:
                    response_size = len(response.get_data())
                except Exception:
                    response_size = 0
            
            # Get real client IP (works with PROXY_FIX enabled)
            client_ip = flask.request.environ.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip() or flask.request.remote_addr
            
            logger = logging.getLogger("superset.http.access")
            
            # Log HTTP access in structured format compatible with GCP Logs Explorer
            # This replaces Gunicorn's plain text access logs
            logger.info(
                f"{flask.request.method} {flask.request.path} HTTP/1.1",
                extra={
                    "http_status_code": response.status_code,
                    "http_method": flask.request.method,
                    "http_path": flask.request.path,
                    "http_url": flask.request.url,
                    "http_referer": flask.request.referrer,
                    "http_user_agent": flask.request.headers.get("User-Agent", ""),
                    "http_remote_addr": client_ip,
                    "response_size_bytes": response_size,
                    "duration_ms": duration_ms,
                    "duration_seconds": duration_seconds,
                }
            )
            
            return response


def install_request_tracking(app: flask.Flask) -> None:
    """
    Install request tracking middleware.
    
    Args:
        app: Flask application instance
    """
    RequestTrackingMiddleware(app)
