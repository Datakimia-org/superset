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
import os
import re
import sys
import traceback
from datetime import datetime
from typing import Any

import flask


class GCPLoggingFilter(logging.Filter):
    """Filter to add request context to log records for GCP Logs Explorer."""
    
    def filter(self, record: logging.LogRecord) -> bool:
        """Add request context (request ID, user, HTTP info, etc.) to log record."""
        try:
            from flask import g, request
            
            # Add request ID if available
            if hasattr(g, "request_id"):
                record.request_id = g.request_id
                record.trace_id = g.request_id  # Use request_id as trace_id for correlation
            else:
                record.request_id = None
                record.trace_id = None
                
            # Add user info if available
            if hasattr(g, "user") and g.user is not None:
                record.user_id = g.user.id if hasattr(g.user, "id") else None
                record.username = g.user.username if hasattr(g.user, "username") else None
            else:
                record.user_id = None
                record.username = None
            
            # Add HTTP request context (useful for filtering in GCP Logs Explorer)
            if request:
                record.http_request_method = request.method
                record.http_request_url = request.url
                record.http_request_path = request.path
                record.http_request_referer = request.referrer
                record.http_request_user_agent = request.headers.get("User-Agent")
                record.http_request_remote_addr = request.remote_addr
                # Get X-Forwarded-For if behind proxy
                record.http_request_x_forwarded_for = request.headers.get("X-Forwarded-For")
                # Trace context from GCP (Cloud Trace)
                record.http_request_trace = request.headers.get("X-Cloud-Trace-Context")
                
                # Extract trace ID from X-Cloud-Trace-Context if present
                # Format: TRACE_ID/SPAN_ID;o=TRACE_TRUE
                if record.http_request_trace and not record.trace_id:
                    trace_parts = record.http_request_trace.split("/")
                    if trace_parts:
                        record.trace_id = trace_parts[0]
            else:
                record.http_request_method = None
                record.http_request_url = None
                record.http_request_path = None
                record.http_request_referer = None
                record.http_request_user_agent = None
                record.http_request_remote_addr = None
                record.http_request_x_forwarded_for = None
                record.http_request_trace = None
            
            # Add logs_context if available (from @logs_context decorator)
            if hasattr(g, "logs_context") and g.logs_context:
                context = g.logs_context
                record.slice_id = context.get("slice_id")
                record.dashboard_id = context.get("dashboard_id")
                record.dataset_id = context.get("dataset_id")
                record.execution_id = context.get("execution_id")
                record.report_schedule_id = context.get("report_schedule_id")
            else:
                record.slice_id = None
                record.dashboard_id = None
                record.dataset_id = None
                record.execution_id = None
                record.report_schedule_id = None
                
        except (RuntimeError, AttributeError):
            # Not in a request context
            record.request_id = None
            record.trace_id = None
            record.user_id = None
            record.username = None
            record.http_request_method = None
            record.http_request_url = None
            record.http_request_path = None
            record.http_request_referer = None
            record.http_request_user_agent = None
            record.http_request_remote_addr = None
            record.http_request_x_forwarded_for = None
            record.http_request_trace = None
            record.slice_id = None
            record.dashboard_id = None
            record.dataset_id = None
            record.execution_id = None
            record.report_schedule_id = None
            
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
    
    # ANSI escape code pattern to strip color codes
    ANSI_ESCAPE_RE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    
    @staticmethod
    def strip_ansi_codes(text: str) -> str:
        """Remove ANSI escape codes from text."""
        return GCPJSONFormatter.ANSI_ESCAPE_RE.sub('', text)
    
    def _get_gcp_project(self) -> str:
        """Get GCP project ID from environment."""
        return os.environ.get("GCP_PROJECT") or os.environ.get("GOOGLE_CLOUD_PROJECT") or "unknown-project"
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        # Strip ANSI codes from message
        message = record.getMessage()
        message = self.strip_ansi_codes(message)
        
        log_entry = {
            "severity": self.LEVEL_MAP.get(record.levelno, "INFO"),
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "logger": record.name,
            "message": message,
        }
        
        # Add source location for better debugging in GCP Logs Explorer
        if hasattr(record, "pathname") and record.pathname:
            log_entry["sourceLocation"] = {
                "file": record.pathname,
                "line": record.lineno,
                "function": record.funcName or "unknown",
            }
        
        # Add trace ID for distributed tracing (GCP Cloud Trace)
        if hasattr(record, "trace_id") and record.trace_id:
            log_entry["trace"] = f"projects/{self._get_gcp_project()}/traces/{record.trace_id}"
        
        # Add request correlation ID
        if hasattr(record, "request_id") and record.request_id:
            log_entry["request_id"] = record.request_id
            
        # Add user context (useful for filtering by user in GCP Logs Explorer)
        if hasattr(record, "user_id") and record.user_id:
            log_entry["user_id"] = record.user_id
            
        if hasattr(record, "username") and record.username:
            log_entry["username"] = record.username
        
        # Add HTTP request context (structured for easy querying in GCP Logs Explorer)
        http_context = {}
        if hasattr(record, "http_request_method") and record.http_request_method:
            http_context["requestMethod"] = record.http_request_method
        if hasattr(record, "http_request_url") and record.http_request_url:
            http_context["requestUrl"] = record.http_request_url
        if hasattr(record, "http_request_path") and record.http_request_path:
            http_context["requestPath"] = record.http_request_path
        if hasattr(record, "http_request_remote_addr") and record.http_request_remote_addr:
            http_context["remoteIp"] = record.http_request_remote_addr
        if hasattr(record, "http_request_referer") and record.http_request_referer:
            http_context["referer"] = record.http_request_referer
        if hasattr(record, "http_request_user_agent") and record.http_request_user_agent:
            http_context["userAgent"] = record.http_request_user_agent
        
        if http_context:
            log_entry["httpRequest"] = http_context
        
        # Add Superset-specific context (dashboard, slice, etc.) for easy filtering
        superset_context = {}
        if hasattr(record, "slice_id") and record.slice_id:
            superset_context["slice_id"] = record.slice_id
        if hasattr(record, "dashboard_id") and record.dashboard_id:
            superset_context["dashboard_id"] = record.dashboard_id
        if hasattr(record, "dataset_id") and record.dataset_id:
            superset_context["dataset_id"] = record.dataset_id
        if hasattr(record, "execution_id") and record.execution_id:
            superset_context["execution_id"] = record.execution_id
        if hasattr(record, "report_schedule_id") and record.report_schedule_id:
            superset_context["report_schedule_id"] = record.report_schedule_id
        
        if superset_context:
            log_entry["superset"] = superset_context
        
        # Add exception info if present
        if record.exc_info:
            exc_type, exc_value, exc_traceback = record.exc_info
            stack_trace = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
            # Strip ANSI codes from stack trace as well
            stack_trace = self.strip_ansi_codes(stack_trace)
            log_entry["exception"] = {
                "type": exc_type.__name__ if exc_type else None,
                "message": str(exc_value) if exc_value else None,
                "stack_trace": stack_trace,
            }
        
        # Add extra fields if present
        if hasattr(record, "__dict__"):
            # Exclude standard LogRecord attributes and our custom fields (already added above)
            excluded = {
                "name", "msg", "args", "created", "filename", "funcName", "levelname",
                "levelno", "lineno", "module", "msecs", "message", "pathname",
                "process", "processName", "relativeCreated", "thread", "threadName",
                "exc_info", "exc_text", "stack_info", "request_id", "trace_id", "user_id", "username",
                "http_request_method", "http_request_url", "http_request_path", "http_request_referer",
                "http_request_user_agent", "http_request_remote_addr", "http_request_x_forwarded_for",
                "http_request_trace", "slice_id", "dashboard_id", "dataset_id", "execution_id",
                "report_schedule_id"
            }
            for key, value in record.__dict__.items():
                if key not in excluded and not key.startswith("_"):
                    # Strip ANSI codes from string values
                    if isinstance(value, str):
                        value = self.strip_ansi_codes(value)
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
