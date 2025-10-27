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
        
        @self.app.before_request
        def log_request_start() -> None:
            """Log request start with request ID."""
            import logging
            logger = logging.getLogger(__name__)
            
            # Get real client IP (works with PROXY_FIX enabled)
            client_ip = flask.request.environ.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip() or flask.request.remote_addr
            
            logger.info(
                "Request started",
                extra={
                    "method": flask.request.method,
                    "path": flask.request.path,
                    "remote_addr": client_ip,
                    "user_agent": flask.request.headers.get("User-Agent", ""),
                    "forwarded_from": flask.request.remote_addr,
                }
            )
        
        @self.app.after_request
        def add_request_id_header(response: flask.Response) -> flask.Response:
            """Add request ID to response headers."""
            response.headers["X-Request-ID"] = flask.g.request_id
            return response
        
        @self.app.after_request
        def log_request_end(response: flask.Response) -> flask.Response:
            """Log request completion with timing and response status."""
            import logging
            import time
            
            # Calculate request duration if start time is available
            duration_ms = None
            if hasattr(flask.g, "request_start_time"):
                duration_seconds = time.time() - flask.g.request_start_time
                duration_ms = int(duration_seconds * 1000)
            
            logger = logging.getLogger(__name__)
            logger.info(
                "Request completed",
                extra={
                    "status_code": response.status_code,
                    "method": flask.request.method,
                    "path": flask.request.path,
                    "duration_ms": duration_ms,
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
