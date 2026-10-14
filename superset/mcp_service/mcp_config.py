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
"""Default MCP service configuration"""

import logging
import re
import secrets
from typing import Any, Dict, Optional

from flask import Flask

from superset.mcp_service.constants import (
    DEFAULT_TOKEN_LIMIT,
    DEFAULT_WARN_THRESHOLD_PCT,
)

logger = logging.getLogger(__name__)

# Public JWKS endpoints. These are not secrets.
_GOOGLE_ISSUER = "https://accounts.google.com"
_GOOGLE_JWKS_URI = "https://www.googleapis.com/oauth2/v3/certs"
_AZURE_TENANT_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9.-]{0,127}")
_AUTH0_DOMAIN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9.-]*\.[A-Za-z]{2,}")
_AZURE_ISSUER_RE = re.compile(
    r"https://login\.microsoftonline\.com/[^/]+/v2\.0/?"
    r"|https://sts\.windows\.net/[^/]+/?"
)


class MCPAuthConfigError(ValueError):
    """MCP auth configuration that must refuse process startup."""


# MCP Service Configuration
# Note: MCP_DEV_USERNAME MUST be configured in superset_config.py
# There is no default value - the service will fail if not set
SUPERSET_WEBSERVER_ADDRESS = "http://localhost:9001"

# WebDriver Configuration for screenshots
WEBDRIVER_BASEURL = "http://localhost:9001/"
WEBDRIVER_BASEURL_USER_FRIENDLY = WEBDRIVER_BASEURL

# MCP Service Host/Port
MCP_SERVICE_HOST = "localhost"
MCP_SERVICE_PORT = 5008

# MCP Debug mode - shows suppressed initialization output in stdio mode
MCP_DEBUG = False

# MCP RBAC - when True, tools with class_permission_name are checked
# against the FAB security_manager before execution.
MCP_RBAC_ENABLED = True

# MCP JWT Debug Errors - controls server-side JWT debug logging.
# When False (default), uses the default JWTVerifier with minimal logging.
# When True, uses DetailedJWTVerifier with tiered logging:
#   - WARNING level: generic failure categories only (e.g. "Issuer mismatch")
#   - DEBUG level: detailed claim values for troubleshooting
#   - Secrets (e.g. HS256 keys) are NEVER logged at any level
# HTTP responses ALWAYS return generic errors regardless of this setting,
# per RFC 6750 Section 3.1. This flag NEVER affects client-facing output.
MCP_JWT_DEBUG_ERRORS = False

# Enable parse_request decorator for MCP tools.
# When True (default), tool requests are automatically parsed from JSON strings
# to Pydantic models, working around a Claude Code double-serialization bug
# (https://github.com/anthropics/claude-code/issues/5504).
# Set to False to disable and let FastMCP handle request parsing natively.
MCP_PARSE_REQUEST_ENABLED = True

# Session configuration for local development
MCP_SESSION_CONFIG = {
    "SESSION_COOKIE_HTTPONLY": True,
    "SESSION_COOKIE_SECURE": False,
    "SESSION_COOKIE_SAMESITE": "Lax",
    "SESSION_COOKIE_NAME": "superset_session",
    "PERMANENT_SESSION_LIFETIME": 86400,
}

# CSRF Protection
MCP_CSRF_CONFIG = {
    "WTF_CSRF_ENABLED": True,
    "WTF_CSRF_TIME_LIMIT": None,
}

# FastMCP Factory Configuration
MCP_FACTORY_CONFIG = {
    "name": None,  # Will derive from APP_NAME in app.py
    "branding": None,  # Will derive from APP_NAME in app.py
    "instructions": None,  # Will use default from app.py (parameterized with branding)
    "auth": None,  # No authentication by default
    "lifespan": None,  # No custom lifespan
    "tools": None,  # Auto-discover tools
    "include_tags": None,  # Include all tags
    "exclude_tags": None,  # Exclude no tags
    "config": None,  # No additional config
}

# =============================================================================
# MCP Storage and Caching Configuration
# =============================================================================
#
# Overview:
# ---------
# MCP caching uses FastMCP's ResponseCachingMiddleware to cache tool responses.
# By default, caching is DISABLED. When enabled, it can use either:
#   1. In-memory store (default) - no additional configuration needed
#   2. Redis store - requires MCP_STORE_CONFIG to be enabled
#
# Configuration Flow:
# -------------------
# - MCP_CACHE_CONFIG controls whether caching is enabled and its TTL settings
# - MCP_STORE_CONFIG controls the Redis store (optional)
#
# Scenarios:
# ----------
# 1. Caching disabled (default):
#    MCP_CACHE_CONFIG["enabled"] = False
#    → No caching, MCP_STORE_CONFIG is ignored
#
# 2. Caching with in-memory store:
#    MCP_CACHE_CONFIG["enabled"] = True
#    MCP_STORE_CONFIG["enabled"] = False (or not configured)
#    → Caching uses FastMCP's default in-memory store, no Prefix wrapper used
#
# 3. Caching with Redis store:
#    MCP_CACHE_CONFIG["enabled"] = True
#    MCP_STORE_CONFIG["enabled"] = True
#    MCP_STORE_CONFIG["CACHE_REDIS_URL"] = "redis://..."
#    → Caching uses Redis with PrefixKeysWrapper
#
# Redis Store Details:
# --------------------
# When MCP_STORE_CONFIG is enabled, it creates a RedisStore wrapped with
# PrefixKeysWrapper (configurable via WRAPPER_TYPE). The wrapper prepends a
# prefix to all keys, allowing multiple features to share the same Redis
# instance with isolated key namespaces. The prefix comes from the consumer
# (e.g., MCP_CACHE_CONFIG["CACHE_KEY_PREFIX"] for caching).
#
# Advanced Usage:
# ---------------
# The store factory (get_mcp_store) can be used independently for custom
# purposes like auth token storage or event logging. Import and call:
#
#   from superset.mcp_service.storage import get_mcp_store
#   my_store = get_mcp_store(prefix="my_feature_v1_")
#
# Currently, the store is only used by the caching layer when enabled.
# =============================================================================

# MCP Store Configuration - shared Redis infrastructure for all MCP storage needs
# (caching, auth, events, session state, etc.).
#
# When CACHE_REDIS_URL is set:
# - Response caching uses Redis (if MCP_CACHE_CONFIG enabled)
# - EventStore uses Redis for multi-pod session management
#
# For multi-pod/Kubernetes deployments, setting CACHE_REDIS_URL automatically
# enables Redis-backed EventStore to share session state across pods.
MCP_STORE_CONFIG: Dict[str, Any] = {
    "enabled": False,  # Disabled by default - caching uses in-memory store
    "CACHE_REDIS_URL": None,  # Redis URL, e.g., "redis://localhost:6379/0"
    # Wrapper class that prefixes all keys. Each consumer provides their own prefix.
    "WRAPPER_TYPE": "key_value.aio.wrappers.prefix_keys.PrefixKeysWrapper",
    # EventStore settings (for multi-pod session management)
    "event_store_max_events": 100,  # Keep last 100 events per session
    "event_store_ttl": 3600,  # Events expire after 1 hour
}

# MCP Response Caching Configuration - controls caching behavior and TTLs
# When enabled without MCP_STORE_CONFIG, uses in-memory store.
# When enabled with MCP_STORE_CONFIG, uses Redis store.
MCP_CACHE_CONFIG: Dict[str, Any] = {
    "enabled": False,  # Disabled by default
    "CACHE_KEY_PREFIX": None,  # Only needed when using the store
    "list_tools_ttl": 60 * 5,  # 5 minutes
    "list_resources_ttl": 60 * 5,  # 5 minutes
    "list_prompts_ttl": 60 * 5,  # 5 minutes
    "read_resource_ttl": 60 * 60,  # 1 hour
    "get_prompt_ttl": 60 * 60,  # 1 hour
    "call_tool_ttl": 60 * 60,  # 1 hour
    "max_item_size": 1024 * 1024,  # 1MB
    "excluded_tools": [  # Tools that should never be cached (side effects, dynamic)
        "execute_sql",
        "generate_dashboard",
        "generate_chart",
        "update_chart",
    ],
}

# =============================================================================
# MCP Response Size Guard Configuration
# =============================================================================
#
# Overview:
# ---------
# The Response Size Guard prevents oversized responses from overwhelming LLM
# clients (e.g., Claude Desktop). When a tool response exceeds the token limit,
# it returns a helpful error with suggestions for reducing the response size.
#
# How it works:
# -------------
# 1. After a tool executes, the middleware estimates the response's token count
# 2. If the response exceeds the configured limit, it blocks the response
# 3. Instead, it returns an error message with smart suggestions:
#    - Reduce page_size/limit
#    - Use select_columns to exclude large fields
#    - Add filters to narrow results
#    - Tool-specific recommendations
#
# Configuration:
# --------------
# - enabled: Toggle the guard on/off (default: True)
# - token_limit: Maximum estimated tokens per response (default: 25,000)
# - excluded_tools: Tools to skip checking (e.g., streaming tools)
# - warn_threshold_pct: Log warnings above this % of limit (default: 80%)
#
# Token Estimation:
# -----------------
# Uses character-based heuristic (~3.5 chars per token for JSON).
# This is intentionally conservative to avoid underestimating.
# =============================================================================
MCP_RESPONSE_SIZE_CONFIG: Dict[str, Any] = {
    "enabled": True,  # Enabled by default to protect LLM clients
    "token_limit": DEFAULT_TOKEN_LIMIT,
    "warn_threshold_pct": DEFAULT_WARN_THRESHOLD_PCT,
    "excluded_tools": [  # Tools to skip size checking
        "health_check",  # Always small
        "get_chart_preview",  # Returns URLs, not data
        "generate_explore_link",  # Returns URLs
        "open_sql_lab_with_context",  # Returns URLs
        "search_tools",  # Returns tool schemas for discovery (intentionally large)
    ],
}


# =============================================================================
# MCP Tool Search Transform Configuration
# =============================================================================
#
# Overview:
# ---------
# When enabled, replaces the full tool catalog with a search interface.
# LLMs see only 2 synthetic tools (search_tools + call_tool) plus any
# pinned tools, and discover other tools on-demand via natural language search.
# This reduces initial context by ~70% (from ~40k tokens to ~5-8k tokens).
#
# Strategies:
# -----------
# - "bm25": Natural language search using BM25 ranking (recommended)
# - "regex": Pattern-based search using regular expressions
#
# Schema Compaction:
# ------------------
# When compact_schemas=True, search results strip $defs sections and replace
# $ref pointers with {"type": "object"}, and truncate tool descriptions.
# This reduces per-search token cost by ~40-60%.  Full schemas remain
# available when the tool is actually invoked via call_tool.
#
# Rollback:
# ---------
# - Set enabled=False to disable tool search entirely (full catalog exposed).
# - Set compact_schemas=False to disable schema compaction only (full $defs
#   and descriptions in search results, tool search still active).
# - Set max_description_length=0 to disable description truncation only.
#
# Summary Mode (include_schemas):
# --------------------------------
# When include_schemas=False (default), search results omit inputSchema
# entirely and include a lightweight "parameters_hint" field listing
# top-level parameter names (e.g. "page, page_size, search, filters").
# This reduces per-search token cost by ~80% vs compact mode while still
# conveying what parameters a tool accepts.  Full schemas remain available
# when invoking the tool via call_tool.
# - Set include_schemas=True to restore full inputSchema in search results.
# - compact_schemas is ignored when include_schemas=False (no schema to
#   compact); max_description_length still applies in summary mode.
# =============================================================================
MCP_TOOL_SEARCH_CONFIG: Dict[str, Any] = {
    "enabled": True,  # Enabled by default — reduces initial context by ~70%
    "strategy": "bm25",  # "bm25" (natural language) or "regex" (pattern matching)
    "max_results": 5,  # Max tools returned per search
    "always_visible": [  # Tools always shown in list_tools (pinned)
        "health_check",
        "get_instance_info",
    ],
    "search_tool_name": "search_tools",  # Name of the search tool
    "call_tool_name": "call_tool",  # Name of the call proxy tool
    "compact_schemas": True,  # Strip $defs/$ref (requires include_schemas=True)
    "max_description_length": 300,  # Truncate tool descriptions (0 = no truncation)
    "include_schemas": False,  # False=summary mode (name+hint), True=full inputSchema
}


def _config_flag(app: Flask, key: str, default: bool = False) -> bool:
    """Read a boolean Flask config value, including string env overrides."""
    value = app.config.get(key, default)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _required_audience(app: Flask) -> str:
    """Return MCP_JWT_AUDIENCE or refuse to build an auth provider."""
    audience = app.config.get("MCP_JWT_AUDIENCE")
    if not isinstance(audience, str) or not audience.strip():
        raise MCPAuthConfigError(
            "MCP_JWT_AUDIENCE must be set when MCP_AUTH_ENABLED is True so that "
            "tokens are bound to this service. Set MCP_JWT_AUDIENCE to the "
            "audience value your identity provider issues for the MCP service."
        )
    return audience.strip()


def _pinned_algorithm(app: Flask) -> str:
    """Return the signing algorithm, rejecting unsigned tokens."""
    algorithm = app.config.get("MCP_JWT_ALGORITHM") or "RS256"
    if not isinstance(algorithm, str) or algorithm.lower() in {"none", ""}:
        raise MCPAuthConfigError(
            "MCP_JWT_ALGORITHM must be a signed algorithm (for example RS256). "
            "Unsigned ('none') tokens are rejected."
        )
    if not app.config.get("MCP_JWT_ALGORITHM"):
        from superset.mcp_service.jwt_verifier import _warn_on_weak_jwt_config

        _warn_on_weak_jwt_config(
            audience=app.config.get("MCP_JWT_AUDIENCE"),
            algorithm=None,
        )
    return algorithm


def _azure_tenant(app: Flask) -> str | None:
    tenant = app.config.get("MCP_AZURE_TENANT_ID")
    if not isinstance(tenant, str) or not tenant.strip():
        return None
    tenant = tenant.strip()
    if not _AZURE_TENANT_RE.fullmatch(tenant):
        raise MCPAuthConfigError(
            "MCP_AZURE_TENANT_ID must be an Azure Entra tenant id or domain."
        )
    return tenant


def _auth0_domain(app: Flask) -> str | None:
    domain = app.config.get("MCP_AUTH0_DOMAIN")
    if not isinstance(domain, str) or not domain.strip():
        return None
    domain = domain.strip().removeprefix("https://").removesuffix("/")
    if "/" in domain or not _AUTH0_DOMAIN_RE.fullmatch(domain):
        raise MCPAuthConfigError(
            "MCP_AUTH0_DOMAIN must be an Auth0 hostname such as tenant.auth0.com."
        )
    return domain


def _google_jwt_enabled(app: Flask, *, idp_bundle: bool) -> bool:
    if "MCP_GOOGLE_JWT_ENABLED" in app.config:
        return _config_flag(app, "MCP_GOOGLE_JWT_ENABLED", False)
    return idp_bundle


def _build_jwt_verifier(
    app: Flask,
    *,
    audience: str,
    algorithm: str,
    issuer: str | list[str] | None,
    jwks_uri: str | None = None,
    public_key: str | None = None,
) -> Any:
    """Build one JWT verifier. IdP verifiers use FastMCP's JWTVerifier."""
    common_kwargs: dict[str, Any] = {
        "issuer": issuer,
        "audience": audience,
        "algorithm": algorithm,
        "required_scopes": app.config.get("MCP_REQUIRED_SCOPES", []),
    }
    if jwks_uri:
        common_kwargs["jwks_uri"] = jwks_uri
    if public_key:
        common_kwargs["public_key"] = public_key

    from fastmcp.server.auth.providers.jwt import JWTVerifier

    return JWTVerifier(**common_kwargs)


def _legacy_jwt_verifier(app: Flask, *, audience: str, algorithm: str) -> Any | None:
    """Verifier for MCP_JWKS_URI / MCP_JWT_PUBLIC_KEY / MCP_JWT_SECRET."""
    jwks_uri = app.config.get("MCP_JWKS_URI")
    public_key = app.config.get("MCP_JWT_PUBLIC_KEY")
    secret = app.config.get("MCP_JWT_SECRET")
    if not (jwks_uri or public_key or secret):
        return None

    issuer = app.config.get("MCP_JWT_ISSUER")
    if not issuer:
        raise MCPAuthConfigError(
            "MCP_JWT_ISSUER must be set when MCP_JWKS_URI, MCP_JWT_PUBLIC_KEY, "
            "or MCP_JWT_SECRET is configured."
        )

    if algorithm == "HS256" and secret:
        verifier_kwargs = {
            "public_key": secret,
            "issuer": issuer,
            "audience": audience,
            "algorithm": "HS256",
            "required_scopes": app.config.get("MCP_REQUIRED_SCOPES", []),
        }
    else:
        verifier_kwargs = {
            "jwks_uri": jwks_uri,
            "public_key": public_key,
            "issuer": issuer,
            "audience": audience,
            "algorithm": algorithm,
            "required_scopes": app.config.get("MCP_REQUIRED_SCOPES", []),
        }

    if app.config.get("MCP_JWT_DEBUG_ERRORS", False):
        from superset.mcp_service.jwt_verifier import DetailedJWTVerifier

        return DetailedJWTVerifier(**verifier_kwargs)

    from fastmcp.server.auth.providers.jwt import JWTVerifier

    return JWTVerifier(**verifier_kwargs)


def _idp_jwt_verifiers(app: Flask, *, audience: str) -> tuple[list[Any], list[str]]:
    """JWT verifiers for Google, Azure Entra, and Auth0 bearer tokens."""
    azure_tenant = _azure_tenant(app)
    auth0_domain = _auth0_domain(app)
    oauth_configured = bool(app.config.get("MCP_OAUTH_CONFIG_URL"))
    idp_bundle = bool(azure_tenant or auth0_domain or oauth_configured)
    verifiers: list[Any] = []
    issuers: list[str] = []

    if _google_jwt_enabled(app, idp_bundle=idp_bundle):
        issuers.append(_GOOGLE_ISSUER)
        verifiers.append(
            _build_jwt_verifier(
                app,
                audience=audience,
                algorithm="RS256",
                issuer=_GOOGLE_ISSUER,
                jwks_uri=_GOOGLE_JWKS_URI,
            )
        )

    if azure_tenant:
        azure_jwks = (
            f"https://login.microsoftonline.com/{azure_tenant}/discovery/v2.0/keys"
        )
        azure_issuers = (
            f"https://login.microsoftonline.com/{azure_tenant}/v2.0",
            f"https://sts.windows.net/{azure_tenant}/",
        )
        issuers.extend(azure_issuers)
        for issuer in azure_issuers:
            verifiers.append(
                _build_jwt_verifier(
                    app,
                    audience=audience,
                    algorithm="RS256",
                    issuer=issuer,
                    jwks_uri=azure_jwks,
                )
            )

    if auth0_domain:
        auth0_issuer = f"https://{auth0_domain}/"
        issuers.append(auth0_issuer)
        verifiers.append(
            _build_jwt_verifier(
                app,
                audience=audience,
                algorithm="RS256",
                issuer=auth0_issuer,
                jwks_uri=f"https://{auth0_domain}/.well-known/jwks.json",
            )
        )
    return verifiers, issuers


# Scopes Claude must receive an ID token for. ``idp_email_user_resolver``
# reads ``iss`` and ``email`` from that token. Access tokens from Google are
# opaque, so verifying them with JWTVerifier never yields those claims.
_CLAUDE_IDENTITY_SCOPES = ("openid", "email", "profile")


def _oauth_upstream_kind(config_url: str) -> str:
    """Classify the upstream issuer from its discovery URL host."""
    from urllib.parse import urlparse

    host = (urlparse(config_url).hostname or "").lower()
    if host == "accounts.google.com" or host.endswith(".google.com"):
        return "google"
    if host.endswith(".microsoftonline.com") or host.endswith(".windows.net"):
        return "microsoft"
    return "oidc"


def _claude_login_scopes(upstream_kind: str) -> list[str]:
    """Scopes advertised to Claude and requested from the identity provider.

    Google refresh tokens come from ``access_type=offline``. Sending
    ``offline_access`` as a scope makes Google reject the authorize redirect.
    Auth0 and Azure Entra issue a refresh token when that scope is requested,
    and Claude adds it only when ``scopes_supported`` lists it.
    """
    scopes = list(_CLAUDE_IDENTITY_SCOPES)
    if upstream_kind != "google":
        scopes.append("offline_access")
    return scopes


def _bind_id_token_verifier(provider: Any, client_id: str) -> Any:
    """Verify the upstream ID token when the provider cannot be told to.

    ``Auth0Provider`` does not accept ``verify_id_token``. Its default
    verifier checks the API access token, which often has no ``email``
    claim. Claude's session is the ID token: audience is the OAuth client
    id (OIDC Core), and ``idp_email_user_resolver`` reads ``iss`` and
    ``email`` from the claims ``JWTVerifier`` already returns.
    """
    oidc_config = getattr(provider, "oidc_config", None)
    if oidc_config is None or not hasattr(provider, "_token_validator"):
        return provider

    from fastmcp.server.auth.providers.jwt import JWTVerifier

    issuer = getattr(oidc_config, "issuer", None)
    provider._verify_id_token = True
    provider._token_validator = JWTVerifier(
        jwks_uri=str(oidc_config.jwks_uri),
        issuer=str(issuer) if issuer else None,
        audience=client_id,
        algorithm="RS256",
    )
    return provider


def _oauth_authorization_server(app: Flask, *, audience: str) -> Any | None:
    """Authorization server that publishes OAuth metadata for Claude.

    ``JWTVerifier`` only checks a Bearer token. Claude discovers
    ``/.well-known/oauth-protected-resource`` and follows the authorization
    redirect, which FastMCP serves from ``Auth0Provider`` or ``OIDCProxy``.

    The proxy then swaps Claude's token for the upstream ID token. That is
    the token ``idp_email_user_resolver`` maps to a Superset user. Redirect
    URIs stay unrestricted so Claude's fixed callback and Claude Code's
    loopback port are both accepted.
    """
    provider = str(app.config.get("MCP_OAUTH_PROVIDER") or "").strip().lower()
    config_url = app.config.get("MCP_OAUTH_CONFIG_URL")
    client_id = app.config.get("MCP_OAUTH_CLIENT_ID")
    client_secret = app.config.get("MCP_OAUTH_CLIENT_SECRET")
    base_url = app.config.get("MCP_OAUTH_BASE_URL")
    if not any((provider, config_url, client_id, client_secret, base_url)):
        return None

    missing = [
        name
        for name, value in (
            ("MCP_OAUTH_CONFIG_URL", config_url),
            ("MCP_OAUTH_CLIENT_ID", client_id),
            ("MCP_OAUTH_CLIENT_SECRET", client_secret),
            ("MCP_OAUTH_BASE_URL", base_url),
        )
        if not value
    ]
    if missing:
        raise MCPAuthConfigError(
            "MCP OAuth authorization server is missing: " + ", ".join(missing)
        )

    config_url_str = str(config_url)
    client_id_str = str(client_id)
    upstream_kind = _oauth_upstream_kind(config_url_str)
    login_scopes = _claude_login_scopes(upstream_kind)

    if provider in {"", "oidc"}:
        from fastmcp.server.auth.oidc_proxy import OIDCProxy

        oidc_kwargs: dict[str, Any] = {
            "config_url": config_url_str,
            "client_id": client_id_str,
            "client_secret": str(client_secret),
            "base_url": str(base_url),
            "algorithm": "RS256",
            "required_scopes": login_scopes,
            "verify_id_token": True,
        }
        # Google and Azure Entra reject ``audience`` on the authorize
        # redirect. Auth0 and other OIDC servers use it to select the API.
        # The ID token audience is still the OAuth client id.
        if upstream_kind == "oidc":
            oidc_kwargs["audience"] = audience
        if upstream_kind == "google":
            oidc_kwargs["extra_authorize_params"] = {"access_type": "offline"}
        return OIDCProxy(**oidc_kwargs)
    if provider == "auth0":
        from fastmcp.server.auth.providers.auth0 import Auth0Provider

        auth0_provider = Auth0Provider(
            config_url=config_url_str,
            client_id=client_id_str,
            client_secret=str(client_secret),
            audience=audience,
            base_url=str(base_url),
            required_scopes=login_scopes,
        )
        return _bind_id_token_verifier(auth0_provider, client_id_str)
    raise MCPAuthConfigError("MCP_OAUTH_PROVIDER must be 'auth0' or 'oidc'.")


def _issuer_values(issuer: Any) -> list[str]:
    if issuer is None:
        return []
    if isinstance(issuer, str):
        return [issuer] if issuer else []
    if isinstance(issuer, (list, tuple, set)):
        return [str(item) for item in issuer if item]
    return [str(issuer)]


def _install_idp_user_resolver(app: Flask, idp_issuers: list[str]) -> None:
    """Record trusted issuers and require an issuer-aware user resolver.

    When more than one issuer is trusted, ``default_user_resolver`` is not
    issuer-scoped. Identity-provider verifiers install
    ``idp_email_user_resolver`` unless the operator already set
    ``MCP_USER_RESOLVER``. A multi-issuer list without either resolver
    refuses startup.
    """
    issuers = _issuer_values(app.config.get("MCP_JWT_ISSUER"))
    issuers.extend(idp_issuers)
    unique_issuers = list(dict.fromkeys(issuers))
    if len(unique_issuers) > 1:
        app.config["MCP_JWT_ISSUER"] = unique_issuers
    if idp_issuers and not app.config.get("MCP_USER_RESOLVER"):
        app.config["MCP_USER_RESOLVER"] = idp_email_user_resolver
    validate_multi_issuer_user_resolver(app)


def create_default_mcp_auth_factory(app: Flask) -> Optional[Any]:
    """Default MCP auth factory using app.config values.

    Accepts Google, Azure Entra, and Auth0 bearer tokens and, when OAuth
    client settings are present, publishes an authorization server so Claude
    can sign in. Claude's session is the upstream ID token, which
    ``idp_email_user_resolver`` maps by email. Does not fall back to
    ``MCP_DEV_USERNAME``.
    """
    if not app.config.get("MCP_AUTH_ENABLED", False):
        return None

    if app.config.get("MCP_DEV_USERNAME"):
        raise MCPAuthConfigError(
            "MCP_DEV_USERNAME must not be set when MCP_AUTH_ENABLED is True: "
            "it would execute callers without a resolvable identity as that "
            "user. Unset MCP_DEV_USERNAME (a development-only convenience)."
        )

    audience = _required_audience(app)
    algorithm = _pinned_algorithm(app)

    try:
        legacy = _legacy_jwt_verifier(app, audience=audience, algorithm=algorithm)
        idp_verifiers, idp_issuers = _idp_jwt_verifiers(app, audience=audience)
        oauth_server = _oauth_authorization_server(app, audience=audience)
    except MCPAuthConfigError:
        raise
    except Exception:
        # Do not log the exception — it may contain the HS256 secret.
        logger.error("Failed to create MCP auth provider")
        raise MCPAuthConfigError(
            "Failed to build the MCP auth provider from the configured auth settings."
        ) from None

    verifiers = [
        verifier for verifier in (legacy, *idp_verifiers) if verifier is not None
    ]
    if not verifiers and oauth_server is None:
        raise MCPAuthConfigError(
            "MCP_AUTH_ENABLED is True but no JWT verifier or OAuth "
            "authorization server is configured."
        )

    _install_idp_user_resolver(app, idp_issuers)

    if oauth_server is not None or len(verifiers) != 1:
        from fastmcp.server.auth import MultiAuth

        # Identity scopes (openid, email, profile) belong to Claude's
        # authorize redirect. Inheriting them here would reject a direct
        # Google, Azure, or Auth0 bearer whose scope claim is different.
        multi_kwargs: dict[str, Any] = {
            "server": oauth_server,
            "verifiers": verifiers,
        }
        if oauth_server is not None:
            multi_kwargs["required_scopes"] = []
        return MultiAuth(**multi_kwargs)
    return verifiers[0]


def default_user_resolver(app: Any, access_token: Any) -> str | None:
    """Extract username from JWT token claims.

    Checks the ``claims`` dict first (FastMCP's AccessToken format),
    then falls back to legacy attribute access for backward compatibility.
    """
    # FastMCP AccessToken stores JWT claims in a dict
    claims = getattr(access_token, "claims", None)
    if isinstance(claims, dict) and claims:
        # Prefer human-readable username claims over opaque `sub`
        # (OIDC `sub` is often a stable opaque ID, not a Superset username)
        username = (
            claims.get("preferred_username")
            or claims.get("username")
            or claims.get("email")
            or claims.get("sub")
        )
        if username:
            return username

    # Legacy attribute access for backward compatibility
    if hasattr(access_token, "subject") and access_token.subject:
        return access_token.subject
    if hasattr(access_token, "client_id") and access_token.client_id:
        return access_token.client_id
    if hasattr(access_token, "payload") and isinstance(access_token.payload, dict):
        return (
            access_token.payload.get("sub")
            or access_token.payload.get("email")
            or access_token.payload.get("username")
        )
    return None


def _is_google_issuer(issuer: str) -> bool:
    normalized = issuer.strip().rstrip("/")
    return normalized in {_GOOGLE_ISSUER, "accounts.google.com"}


def _is_azure_entra_issuer(issuer: str) -> bool:
    return _AZURE_ISSUER_RE.fullmatch(issuer.strip()) is not None


def _is_auth0_issuer(issuer: str, app: Any) -> bool:
    """True when ``issuer`` is Auth0, including a configured custom domain."""
    from urllib.parse import urlparse

    parsed = urlparse(issuer if "://" in issuer else f"https://{issuer}")
    host = (parsed.hostname or "").lower()
    if not host:
        return False
    if host.endswith(".auth0.com"):
        return True
    configured = app.config.get("MCP_AUTH0_DOMAIN")
    if isinstance(configured, str) and configured.strip():
        configured_host = (
            configured.strip().removeprefix("https://").removesuffix("/").split("/")[0]
        )
        return host == configured_host.lower()
    return False


def _email_shaped_claim(value: Any) -> str | None:
    """Return one email address, or None.

    Azure guest UPNs look like ``user_gmail.com#EXT#@tenant.onmicrosoft.com``.
    That string is not the person's mailbox, so it is not a Superset login.
    """
    if not isinstance(value, str):
        return None
    email = value.strip()
    if "@" not in email or any(char.isspace() for char in email):
        return None
    if "#EXT#" in email.upper():
        return None
    return email


def idp_email_user_resolver(app: Any, access_token: Any) -> str:
    """Map a Google, Azure Entra, or Auth0 token to a Superset user email.

    The default resolver matches ``preferred_username`` / ``username`` and
    does not bind ``iss``. This resolver fails closed unless ``iss`` is one
    of those three providers and the token carries an email. The caller
    loads the Superset user by that email.

    Google and Auth0 ID tokens include ``email_verified``. A missing or
    false claim is rejected, so an unverified address cannot match a
    Superset user. Azure Entra does not emit ``email_verified``; the tenant
    is the authority, and an explicit ``false`` is still rejected. Azure
    access and ID tokens often omit ``email`` and put the mailbox in
    ``preferred_username`` or ``upn``. Those claims are accepted only for
    Azure, and only when the value is a single email address.
    """
    claims = getattr(access_token, "claims", None)
    if not isinstance(claims, dict):
        raise ValueError("JWT identity provider token has no claims")

    issuer = claims.get("iss")
    if not isinstance(issuer, str) or not (
        _is_google_issuer(issuer)
        or _is_azure_entra_issuer(issuer)
        or _is_auth0_issuer(issuer, app)
    ):
        raise ValueError("JWT issuer is not Google, Azure Entra, or Auth0")

    if _is_azure_entra_issuer(issuer):
        email = (
            _email_shaped_claim(claims.get("email"))
            or _email_shaped_claim(claims.get("preferred_username"))
            or _email_shaped_claim(claims.get("upn"))
        )
        issuer_emits_verified = False
    else:
        email = _email_shaped_claim(claims.get("email"))
        issuer_emits_verified = True

    if email is None:
        raise ValueError("JWT identity provider token is missing an email claim")

    verified = claims.get("email_verified")
    if verified is not True and (verified is not None or issuer_emits_verified):
        raise ValueError("JWT identity provider email is not verified")
    return email


def validate_multi_issuer_user_resolver(app: Flask) -> None:
    """Reject a multi-issuer JWT trust config that has no issuer-aware resolver.

    ``default_user_resolver`` maps token claims to Superset users by
    username/email without binding the token's ``iss`` claim. When more than
    one issuer is trusted (``MCP_JWT_ISSUER`` configured as a list/tuple/set),
    that lookup is not issuer-scoped: distinct issuers minting the same
    username or email claim would resolve to the identical Superset user.
    Single-issuer deployments are unaffected — the issuer is already pinned
    by the verifier, so the username space is unambiguous.

    Operators trusting more than one issuer must supply an ``MCP_USER_RESOLVER``
    that derives its identity from the token's ``iss`` claim. For Google,
    Azure Entra, and Auth0 that resolver is ``idp_email_user_resolver``,
    which looks the person up by email.
    """
    configured_issuer = app.config.get("MCP_JWT_ISSUER")
    if (
        isinstance(configured_issuer, (list, tuple, set))
        # str()-normalize before deduplicating: a plain set() would raise
        # TypeError on unhashable entries (e.g. an accidental nested list),
        # and that TypeError is not MCPAuthConfigError, so the caller's
        # except MCPAuthConfigError / except Exception split would swallow
        # it and fail OPEN (start unauthenticated) instead of fail closed.
        and len({str(issuer) for issuer in configured_issuer}) > 1
        and not app.config.get("MCP_USER_RESOLVER")
    ):
        raise MCPAuthConfigError(
            "MCP_JWT_ISSUER trusts multiple issuers but no MCP_USER_RESOLVER "
            "is configured. The default user resolver maps token claims to "
            "Superset users by username/email without binding the issuer, so "
            "distinct trusted issuers minting the same username/email would "
            "resolve to the same Superset user. This check only confirms a "
            "resolver is configured, not that it binds the issuer — the "
            "configured MCP_USER_RESOLVER MUST derive its identity from the "
            "token's iss claim (e.g. a compound iss+sub identity), not just "
            "username/email, or the same collision risk persists under a "
            "custom resolver that happens to be username/email-only too."
        )


def generate_secret_key() -> str:
    """Generate a secure random secret key."""
    return secrets.token_urlsafe(42)


def get_mcp_config(app_config: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """
    Get complete MCP configuration dictionary.

    Reads from app_config first, then falls back to defaults if values are not provided.

    Args:
        app_config: Optional Flask app configuration dict to read values from
    """
    app_config = app_config or {}

    # Default MCP configuration
    defaults = {
        "SUPERSET_WEBSERVER_ADDRESS": SUPERSET_WEBSERVER_ADDRESS,
        "WEBDRIVER_BASEURL": WEBDRIVER_BASEURL,
        "WEBDRIVER_BASEURL_USER_FRIENDLY": WEBDRIVER_BASEURL_USER_FRIENDLY,
        "MCP_SERVICE_HOST": MCP_SERVICE_HOST,
        "MCP_SERVICE_PORT": MCP_SERVICE_PORT,
        "MCP_DEBUG": MCP_DEBUG,
        "MCP_RBAC_ENABLED": MCP_RBAC_ENABLED,
        **MCP_SESSION_CONFIG,
        **MCP_CSRF_CONFIG,
    }

    # Merge app_config over defaults - app_config takes precedence
    return {**defaults, **{k: v for k, v in app_config.items() if k in defaults}}


def get_mcp_config_with_overrides(
    app_config: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """
    Alternative approach: Allow any app_config keys, not just predefined ones.

    This version lets users add custom MCP config keys in superset_config.py
    that aren't predefined in the defaults.
    """
    app_config = app_config or {}
    defaults = get_mcp_config()

    # Start with defaults, then overlay any app_config values
    return {**defaults, **app_config}


def get_mcp_factory_config() -> Dict[str, Any]:
    """
    Get FastMCP factory configuration.

    This can be customized by users to provide their own auth providers,
    middleware, lifespan handlers, and other FastMCP configuration.

    Returns:
        Dictionary of FastMCP factory configuration options
    """
    return MCP_FACTORY_CONFIG.copy()
