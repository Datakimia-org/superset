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

"""Guest /chart/data response-cache isolation (token claims, not SQL)."""

from typing import Optional
from unittest.mock import patch

from flask import g

from superset.charts.data.cache_keys import (
    chart_data_api_cache_key,
    guest_chart_data_cache_context,
)
from superset.security.guest_token import GuestTokenResourceType, GuestUser

DASHBOARD_RESOURCE = [
    {"type": GuestTokenResourceType.DASHBOARD, "id": "dash-shared-uuid"}
]
SAME_BODY = {
    "datasource": {"id": 1, "type": "table"},
    "queries": [{"filters": [{"col": "gender", "op": "==", "val": "boy"}]}],
    "result_format": "json",
    "result_type": "full",
}


def _guest(
    username: Optional[str],
    rls: list,
    resources: Optional[list] = None,
) -> GuestUser:
    user: dict = {}
    if username is not None:
        user["username"] = username
    return GuestUser(
        token={
            "user": user,
            "resources": resources if resources is not None else DASHBOARD_RESOURCE,
            "rls_rules": rls,
            "iat": 1.0,
            "exp": 2.0,
        },
        roles=[],
    )


def _key_for(guest: GuestUser, body: Optional[dict] = None) -> str:
    g.user = guest
    return chart_data_api_cache_key(
        body or SAME_BODY,
        guest_chart_data_cache_context(guest),
    )


@patch.dict(
    "superset.extensions.feature_flag_manager._feature_flags",
    EMBEDDED_SUPERSET=True,
)
def test_two_guests_different_username_same_dashboard_filters_have_different_keys(
    app_context: None,
) -> None:
    """Tenancy in username: same dashboard + filters must not share a cache key."""
    tenant_a = _guest("tenant_a", [])
    tenant_b = _guest("tenant_b", [])

    key_a = _key_for(tenant_a)
    key_b = _key_for(tenant_b)

    assert key_a.startswith("chart_data_api:")
    assert key_b.startswith("chart_data_api:")
    context_a, body_a = key_a.split(":")[1:]
    context_b, body_b = key_b.split(":")[1:]
    assert body_a == body_b
    assert context_a != context_b
    assert key_a != key_b


@patch.dict(
    "superset.extensions.feature_flag_manager._feature_flags",
    EMBEDDED_SUPERSET=True,
)
def test_two_guests_different_rls_same_dashboard_filters_have_different_keys(
    app_context: None,
) -> None:
    """Tenancy in rls_rules: isolation must not depend on generated SQL."""
    tenant_a = _guest("guest_user", [{"clause": "client_id = 1"}])
    tenant_b = _guest("guest_user", [{"clause": "client_id = 2"}])

    key_a = _key_for(tenant_a)
    key_b = _key_for(tenant_b)
    assert key_a != key_b
    assert key_a.split(":")[2] == key_b.split(":")[2]


@patch.dict(
    "superset.extensions.feature_flag_manager._feature_flags",
    EMBEDDED_SUPERSET=True,
)
def test_omitted_username_defaults_to_guest_user_and_isolates_via_rls(
    app_context: None,
) -> None:
    """If Portal omits user.username, GuestUser is guest_user; rls_rules still isolate."""
    omitted_a = _guest(None, [{"clause": "org = 'acme'"}])
    omitted_b = _guest(None, [{"clause": "org = 'globex'"}])

    assert omitted_a.username == "guest_user"
    assert omitted_b.username == "guest_user"
    assert _key_for(omitted_a) != _key_for(omitted_b)
