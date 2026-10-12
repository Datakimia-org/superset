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

from superset.mcp_service.system.schemas import RoleInfo


class _PermissionView:
    def __str__(self) -> str:
        return "can read on Chart"


class _Role:
    id = 7
    name = "Admin"
    permissions = [_PermissionView(), "can write on Dashboard"]


def test_role_info_serializes_permission_objects_as_strings() -> None:
    """Dashboard roles carry FAB PermissionView objects, not plain strings."""
    role = RoleInfo.model_validate(_Role(), from_attributes=True)

    assert role.permissions == ["can read on Chart", "can write on Dashboard"]
    assert role.model_dump()["permissions"] == [
        "can read on Chart",
        "can write on Dashboard",
    ]
