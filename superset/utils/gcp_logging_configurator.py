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
Custom logging configuration for GCP Logging.

This module provides structured logging that is compatible with Google Cloud Logging
and includes request correlation IDs for better traceability.
"""
import json
import logging
import sys
import traceback
from datetime import datetime
from typing import Any

import flask


class GCPLoggingFilter(logging.Filter):
    """Filter to add request context to log records."""
    
    def filter(self, record: logging.LogRecord) -> bool:
        """Add request context (request ID, user, etc.) to log record."""
        # Add request ID if available
        try:
            from flask import g
            if hasattr(g, "request_id"):
                record.request_id = g.request_id
            else:
                record.request_id = None
                
            # Add user info if available
            if hasattr(g, "user") and g.user is not None:
                record.user_id = g.user.id if hasattr(g.user, "id") else None
                record.username = g.user.username if hasattr(g.user, "username") else None
            else:
                record.user_id = None
                record.username = None
                
        except (RuntimeError, AttributeError):
            # Not in a request context
            record.request_id = None
            record.user_id = None
            record.username = None
            
        return True


class GCPJSONFormatter(logging.Formatter):
    """JSON formatter compatible with GCP Logging."""
    
    # Map Python log levels to GCP severity levels
    LEVEL_MAP = {
        logging.DEBUG: "DEBUG",
        logging.INFO: "INFO",
        logging.WARNING: "WARNING",
        logging.ERROR: "ERROR",
        logging.CRITICAL: "CRITICAL",
    }
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_entry = {
            "severity": self.LEVEL_MAP.get(record.levelno, "INFO"),
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        # Add request context if available
        if hasattr(record, "request_id") and record.request_id:
            log_entry["request_id"] = record.request_id
            
        if hasattr(record, "user_id") and record.user_id:
            log_entry["user_id"] = record.user_id
            
        if hasattr(record, "username") and record.username:
            log_entry["username"] = record.username
        
        # Add exception info if present
        if record.exc_info:
            exc_type, exc_value, exc_traceback = record.exc_info
            log_entry["exception"] = {
                "type": exc_type.__name__ if exc_type else None,
                "message": str(exc_value) if exc_value else None,
                "stack_trace": "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
            }
        
        # Add extra fields if present
        if hasattr(record, "__dict__"):
            # Exclude standard LogRecord attributes
            excluded = {
                "name", "msg", "args", "created", "filename", "funcName", "levelname",
                "levelno", "lineno", "module", "msecs", "message", "pathname",
                "process", "processName", "relativeCreated", "thread", "threadName",
                "exc_info", "exc_text", "stack_info", "request_id", "user_id", "username"
            }
            for key, value in record.__dict__.items():
                if key not in excluded and not key.startswith("_"):
                    log_entry[key] = value
        
        return json.dumps(log_entry)


class GCPLoggingConfigurator:
    """
    Configurator for GCP-compatible structured logging.
    
    This configurator sets up JSON-based logging that works well with Google Cloud Logging.
    It includes:
    - Structured JSON format
    - Request correlation IDs
    - User context
    - Proper severity mapping
    """
    
    def __init__(self, enable_console_handler: bool = True):
        self.enable_console_handler = enable_console_handler
        
    def configure_logging(
        self, app_config: flask.config.Config, debug_mode: bool
    ) -> None:
        """Configure logging for GCP compatibility."""
        
        # Silence FAB if configured
        if app_config.get("SILENCE_FAB", False):
            logging.getLogger("flask_appbuilder").setLevel(logging.ERROR)
        
        # Get root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(app_config.get("LOG_LEVEL", logging.INFO))
        
        # Remove existing handlers to avoid duplicates
        root_logger.handlers.clear()
        
        # Add GCP logging filter
        gcp_filter = GCPLoggingFilter()
        
        if self.enable_console_handler:
            # Console handler with JSON formatting for GCP
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(GCPJSONFormatter())
            console_handler.addFilter(gcp_filter)
            root_logger.addHandler(console_handler)
        
        # Add file handler if time rotation is enabled
        if app_config.get("ENABLE_TIME_ROTATE", False):
            from logging.handlers import TimedRotatingFileHandler
            
            file_handler = TimedRotatingFileHandler(
                app_config.get("FILENAME", "superset.log"),
                when=app_config.get("ROLLOVER", "midnight"),
                interval=app_config.get("INTERVAL", 1),
                backupCount=app_config.get("BACKUP_COUNT", 30),
            )
            file_handler.setFormatter(GCPJSONFormatter())
            file_handler.addFilter(gcp_filter)
            file_handler.setLevel(app_config.get("TIME_ROTATE_LOG_LEVEL", logging.DEBUG))
            root_logger.addHandler(file_handler)
        
        # Set levels for specific loggers
        logging.getLogger("werkzeug").setLevel(logging.WARNING)
        logging.getLogger("flask_appbuilder").setLevel(logging.INFO)
        
        logging.info("GCP logging configured successfully")
