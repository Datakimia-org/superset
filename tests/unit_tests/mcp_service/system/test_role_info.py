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

from superset.mcp_service.dashboard.schemas import serialize_role_object


class _Named:
    def __init__(self, name: str) -> None:
        self.name = name


class _PermissionView:
    """FAB PermissionView has no name; the label comes from its relations."""

    def __init__(self) -> None:
        self.permission = _Named("can_read")
        self.view_menu = _Named("Chart")


class _Role:
    id = 7
    name = "Admin"
    permissions = [_PermissionView()]


def test_serialize_role_object_formats_permission_view() -> None:
    """PermissionView objects serialize as '{permission.name} on {view_menu.name}'."""
    role = serialize_role_object(_Role())

    assert role is not None
    assert role.permissions == ["can_read on Chart"]
