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
Two-guest /chart/data cache isolation.

A cache HIT returns stored JSON without ChartDataCommand.validate().
Tenancy must be in the guest token (username / resources / rls_rules);
"dashboard looks right" on a cold cache is not a pass.

Calls ChartDataRestApi.data() inside test_request_context with login_user(guest),
matching chart/api_tests.py guest mocks (has_guest_access) without fighting
Flask-Login session cookies on the test client.
"""

from unittest.mock import patch

import pytest
from flask import current_app, g
from superset import security_manager
from superset.charts.data.api import ChartDataRestApi
from superset.charts.data.cache_keys import (
    chart_data_api_cache_key,
    guest_chart_data_cache_context,
)
from superset.daos.dashboard import EmbeddedDashboardDAO
from superset.extensions import cache_manager
from superset.security.guest_token import GuestTokenResourceType
from superset.utils import json
from tests.integration_tests.base_tests import SupersetTestCase
from tests.integration_tests.fixtures.birth_names_dashboard import (
    load_birth_names_dashboard_with_slices,  # noqa: F401
    load_birth_names_data,  # noqa: F401
)
from tests.integration_tests.fixtures.query_context import get_query_context
from tests.integration_tests.test_app import app

CHART_DATA_URI = "api/v1/chart/data"


@patch.dict(
    "superset.extensions.feature_flag_manager._feature_flags",
    EMBEDDED_SUPERSET=True,
)
@pytest.mark.usefixtures("load_birth_names_dashboard_with_slices")
class TestGuestChartDataCacheIsolation(SupersetTestCase):
    def setUp(self) -> None:
        self.dash = self.get_dash_by_slug("births")
        self.embedded = EmbeddedDashboardDAO.upsert(self.dash, [])
        self.chart = self.get_slice("Girls")

        self.payload = get_query_context("birth_names")
        self.payload["datasource"] = {
            "id": self.chart.datasource_id,
            "type": self.chart.datasource_type,
        }
        self.payload["result_format"] = "json"
        self.payload["result_type"] = "full"
        self.payload["form_data"] = {
            "dashboardId": self.dash.id,
            "slice_id": self.chart.id,
            "metrics": self.chart.params_dict.get("metrics"),
        }

        dataset = self.get_table(name="birth_names")
        self.rls_alice = [{"dataset": dataset.id, "clause": "name = 'Alice'"}]
        self.rls_bob = [{"dataset": dataset.id, "clause": "name = 'Bob'"}]
        self.resources = [
            {
                "type": GuestTokenResourceType.DASHBOARD.value,
                "id": str(self.embedded.uuid),
            }
        ]

    def tearDown(self) -> None:
        cache_manager.cache.clear()
        super().tearDown()

    def _token(self, username: str, rls: list) -> str:
        raw = security_manager.create_guest_access_token(
            {"username": username},
            self.resources,
            rls,
        )
        if isinstance(raw, (bytes, bytearray)):
            return raw.decode()
        return raw

    def _guest_from_token(self, token: str):
        header_name = current_app.config["GUEST_TOKEN_HEADER_NAME"]

        class _Req:
            headers = {header_name: token}

            class form:
                @staticmethod
                def get(_name: str) -> None:
                    return None

        guest = security_manager.get_guest_user_from_request(_Req())
        assert guest is not None
        return guest

    def _expected_key(self, token: str) -> str:
        guest = self._guest_from_token(token)
        return chart_data_api_cache_key(
            self.payload,
            guest_chart_data_cache_context(guest),
        )

    def _post(self, token: str):
        header_name = current_app.config["GUEST_TOKEN_HEADER_NAME"]
        guest = self._guest_from_token(token)

        def _is_guest_user(user=None):
            subject = user if user is not None else g.user
            return getattr(subject, "is_guest_user", False)

        with app.test_request_context(
            CHART_DATA_URI,
            method="POST",
            json=self.payload,
            headers={header_name: token},
        ):
            g.user = guest
            with patch.object(security_manager, "has_guest_access", return_value=True):
                with patch.object(
                    security_manager, "is_guest_user", side_effect=_is_guest_user
                ):
                    return ChartDataRestApi().data()

    def test_two_guests_different_tenancy_different_keys_and_payloads(self) -> None:
        token_a = self._token("tenant_a", self.rls_alice)
        token_b = self._token("tenant_b", self.rls_bob)

        key_a = self._expected_key(token_a)
        key_b = self._expected_key(token_b)
        _, context_a, body_a = key_a.split(":", 2)
        _, context_b, body_b = key_b.split(":", 2)

        assert key_a.startswith("chart_data_api:")
        assert key_b.startswith("chart_data_api:")
        assert body_a == body_b
        assert context_a != context_b
        assert key_a != key_b

        captured: list[str] = []
        original_set = cache_manager.cache.set

        def recording_set(key, value, timeout=None):
            captured.append(key)
            return original_set(key, value, timeout=timeout)

        with patch.object(cache_manager.cache, "set", side_effect=recording_set):
            resp_a = self._post(token_a)
            resp_b = self._post(token_b)

        assert resp_a.status_code == 200, resp_a.get_data(as_text=True)
        assert resp_b.status_code == 200, resp_b.get_data(as_text=True)
        assert resp_a.headers.get("X-Chart-Data-API-Cache") == "MISS"
        assert resp_b.headers.get("X-Chart-Data-API-Cache") == "MISS"
        assert key_a in captured
        assert key_b in captured

        payload_a = json.loads(resp_a.get_data(as_text=True))
        payload_b = json.loads(resp_b.get_data(as_text=True))
        assert payload_a != payload_b

        # HIT must not skip validation into the other tenant's rows.
        resp_a_hit = self._post(token_a)
        assert resp_a_hit.headers.get("X-Chart-Data-API-Cache") == "HIT"
        assert json.loads(resp_a_hit.get_data(as_text=True)) == payload_a
        assert json.loads(resp_a_hit.get_data(as_text=True)) != payload_b

        resp_b_again = self._post(token_b)
        assert json.loads(resp_b_again.get_data(as_text=True)) == payload_b
        assert json.loads(resp_b_again.get_data(as_text=True)) != payload_a
