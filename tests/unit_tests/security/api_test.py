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
import pytest

from superset.extensions import appbuilder, csrf
from superset.security.manager import SupersetPermissionViewMenuApi


@pytest.mark.parametrize(
    "app",
    [{"WTF_CSRF_ENABLED": True}],
    indirect=True,
)
def test_csrf_not_exempt(app_context: None) -> None:
    """
    Test that REST API is not exempt from CSRF.
    """
    assert {blueprint.name for blueprint in csrf._exempt_blueprints} == {
        "GroupApi",
        "MenuApi",
        "SecurityApi",
        "OpenApi",
        "SupersetPermissionViewMenuApi",
        "SupersetRoleApi",
        "SupersetUserApi",
        "PermissionApi",
        "ViewMenuApi",
    }


def test_permission_view_menu_api_allows_role_form_filters(app_context: None) -> None:
    """Role edit can search permissions by name and resolve existing ids."""
    api = next(
        view
        for view in appbuilder.baseviews
        if isinstance(view, SupersetPermissionViewMenuApi)
    )

    assert "id" in api._filters.search_columns
    assert "permission.name" in api._filters.search_columns
    assert "view_menu.name" in api._filters.search_columns
    assert any(
        flt.arg_name == "ct" for flt in api._filters._search_filters["permission.name"]
    )
    assert any(
        flt.arg_name == "ct" for flt in api._filters._search_filters["view_menu.name"]
    )
