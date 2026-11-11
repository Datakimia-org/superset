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

"""MCP identity-provider auth factory tests."""

from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from fastmcp.server.auth import MultiAuth

from superset.mcp_service.mcp_config import (
    _bind_id_token_verifier,
    create_default_mcp_auth_factory,
    idp_email_user_resolver,
    MCPAuthConfigError,
    validate_multi_issuer_user_resolver,
)
from superset.mcp_service.server import _create_auth_provider


def _app(**config: object) -> Any:
    return SimpleNamespace(config=dict(config))


def test_auth_enabled_with_dev_username_refuses_startup() -> None:
    app = _app(
        MCP_AUTH_ENABLED=True,
        MCP_DEV_USERNAME="admin",
        MCP_JWT_AUDIENCE="api://superset",
    )

    with pytest.raises(MCPAuthConfigError, match="MCP_DEV_USERNAME"):
        create_default_mcp_auth_factory(app)


def test_auth_enabled_without_audience_refuses_startup() -> None:
    app = _app(
        MCP_AUTH_ENABLED=True, MCP_JWKS_URI="https://example/.well-known/jwks.json"
    )

    with pytest.raises(MCPAuthConfigError, match="MCP_JWT_AUDIENCE"):
        create_default_mcp_auth_factory(app)


def test_unsigned_algorithm_refuses_startup() -> None:
    app = _app(
        MCP_AUTH_ENABLED=True,
        MCP_JWT_AUDIENCE="api://superset",
        MCP_JWT_ALGORITHM="none",
        MCP_GOOGLE_JWT_ENABLED=True,
    )

    with pytest.raises(MCPAuthConfigError, match="none"):
        create_default_mcp_auth_factory(app)


def test_multi_issuer_without_resolver_refuses_startup() -> None:
    app = _app(MCP_JWT_ISSUER=["https://a.example", "https://b.example"])

    with pytest.raises(MCPAuthConfigError, match="MCP_USER_RESOLVER"):
        validate_multi_issuer_user_resolver(app)


def test_idp_factory_installs_email_resolver_and_verifiers() -> None:
    app = _app(
        MCP_AUTH_ENABLED=True,
        MCP_JWT_AUDIENCE="api://superset",
        MCP_GOOGLE_JWT_ENABLED=True,
        MCP_AZURE_TENANT_ID="contoso.onmicrosoft.com",
        MCP_AUTH0_DOMAIN="tenant.auth0.com",
    )

    provider = create_default_mcp_auth_factory(app)

    assert isinstance(provider, MultiAuth)
    assert provider.server is None
    issuers = {verifier.issuer for verifier in provider.verifiers}
    assert "https://accounts.google.com" in issuers
    assert "https://login.microsoftonline.com/contoso.onmicrosoft.com/v2.0" in issuers
    assert "https://sts.windows.net/contoso.onmicrosoft.com/" in issuers
    assert "https://tenant.auth0.com/" in issuers
    assert all(verifier.audience == "api://superset" for verifier in provider.verifiers)
    assert app.config["MCP_USER_RESOLVER"] is idp_email_user_resolver


def test_oauth_server_is_configurable_for_claude_metadata() -> None:
    app = _app(
        MCP_AUTH_ENABLED=True,
        MCP_JWT_AUDIENCE="api://superset",
        MCP_GOOGLE_JWT_ENABLED=True,
        MCP_OAUTH_PROVIDER="oidc",
        MCP_OAUTH_CONFIG_URL="https://login.example/.well-known/openid-configuration",
        MCP_OAUTH_CLIENT_ID="client-id",
        MCP_OAUTH_CLIENT_SECRET="client-secret",  # noqa: S106
        MCP_OAUTH_BASE_URL="https://mcp.example.com",
    )
    sentinel = SimpleNamespace(
        base_url="https://mcp.example.com",
        required_scopes=["openid", "email", "profile"],
        set_mcp_path=lambda path: None,
        get_routes=lambda mcp_path=None: ["oauth-route"],
        get_well_known_routes=lambda mcp_path=None: ["oauth-protected-resource"],
    )

    with patch(
        "fastmcp.server.auth.oidc_proxy.OIDCProxy",
        return_value=sentinel,
    ) as oidc:
        provider = create_default_mcp_auth_factory(app)

    oidc.assert_called_once()
    assert oidc.call_args.kwargs["config_url"].endswith("openid-configuration")
    assert oidc.call_args.kwargs["audience"] == "api://superset"
    assert oidc.call_args.kwargs["verify_id_token"] is True
    assert oidc.call_args.kwargs["required_scopes"] == [
        "openid",
        "email",
        "profile",
        "offline_access",
    ]
    assert isinstance(provider, MultiAuth)
    assert provider.server is sentinel
    # Claude's identity scopes must not become a global gate for direct bearers.
    assert provider.required_scopes == []
    assert provider.get_well_known_routes() == ["oauth-protected-resource"]
    google_issuers = [verifier.issuer for verifier in provider.verifiers]
    assert "https://accounts.google.com" in google_issuers


def test_google_claude_login_does_not_send_audience_param() -> None:
    app = _app(
        MCP_AUTH_ENABLED=True,
        MCP_JWT_AUDIENCE="api://superset",
        MCP_GOOGLE_JWT_ENABLED=False,
        MCP_OAUTH_PROVIDER="oidc",
        MCP_OAUTH_CONFIG_URL="https://accounts.google.com/.well-known/openid-configuration",
        MCP_OAUTH_CLIENT_ID="google-client",
        MCP_OAUTH_CLIENT_SECRET="client-secret",  # noqa: S106
        MCP_OAUTH_BASE_URL="https://mcp.example.com",
    )
    sentinel = SimpleNamespace(
        base_url="https://mcp.example.com",
        required_scopes=["openid", "email", "profile"],
        set_mcp_path=lambda path: None,
        get_routes=lambda mcp_path=None: [],
        get_well_known_routes=lambda mcp_path=None: [],
    )

    with patch(
        "fastmcp.server.auth.oidc_proxy.OIDCProxy",
        return_value=sentinel,
    ) as oidc:
        create_default_mcp_auth_factory(app)

    assert "audience" not in oidc.call_args.kwargs
    assert oidc.call_args.kwargs["verify_id_token"] is True
    assert oidc.call_args.kwargs["required_scopes"] == ["openid", "email", "profile"]
    assert oidc.call_args.kwargs["extra_authorize_params"] == {"access_type": "offline"}


def test_auth0_provider_selected_by_environment() -> None:
    app = _app(
        MCP_AUTH_ENABLED=True,
        MCP_JWT_AUDIENCE="api://superset",
        MCP_GOOGLE_JWT_ENABLED=False,
        MCP_OAUTH_PROVIDER="auth0",
        MCP_OAUTH_CONFIG_URL="https://tenant.auth0.com/.well-known/openid-configuration",
        MCP_OAUTH_CLIENT_ID="client-id",
        MCP_OAUTH_CLIENT_SECRET="client-secret",  # noqa: S106
        MCP_OAUTH_BASE_URL="https://mcp.example.com",
    )
    sentinel = SimpleNamespace(
        base_url="https://mcp.example.com",
        required_scopes=["openid"],
        set_mcp_path=lambda path: None,
    )

    with patch(
        "fastmcp.server.auth.providers.auth0.Auth0Provider",
        return_value=sentinel,
    ) as auth0:
        provider = create_default_mcp_auth_factory(app)

    auth0.assert_called_once()
    assert auth0.call_args.kwargs["audience"] == "api://superset"
    assert auth0.call_args.kwargs["required_scopes"] == [
        "openid",
        "email",
        "profile",
        "offline_access",
    ]
    assert isinstance(provider, MultiAuth)
    assert provider.server is sentinel
    assert provider.required_scopes == []
    assert provider.verifiers == []


def test_auth0_claude_login_verifies_id_token() -> None:
    oidc_config = SimpleNamespace(
        jwks_uri="https://tenant.auth0.com/.well-known/jwks.json",
        issuer="https://tenant.auth0.com/",
    )
    provider = SimpleNamespace(
        oidc_config=oidc_config,
        _token_validator=None,
        _verify_id_token=False,
    )

    bound = _bind_id_token_verifier(provider, "auth0-client")

    assert bound._verify_id_token is True
    assert bound._token_validator.audience == "auth0-client"
    assert bound._token_validator.issuer == "https://tenant.auth0.com/"
    assert bound._token_validator.algorithm == "RS256"
    assert bound._token_validator.required_scopes == []


def test_create_auth_provider_propagates_config_error() -> None:
    app = _app(MCP_AUTH_ENABLED=True, MCP_DEV_USERNAME="admin", MCP_JWT_AUDIENCE="api")

    with pytest.raises(MCPAuthConfigError, match="MCP_DEV_USERNAME"):
        _create_auth_provider(app)
