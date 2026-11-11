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
"""Response-cache key helpers for chart data API (guest token claims, not SQL)."""

from __future__ import annotations

from typing import Any, Union

from superset.utils.hashing import md5_sha_from_dict


def guest_chart_data_cache_context(guest_user: Any) -> str:
    """MD5 context for embedded guests: username + resources + rls from JWT."""
    cache_payload = {
        "username": getattr(guest_user, "username", None),
        "resources": getattr(guest_user, "resources", None),
        "rls": getattr(guest_user, "rls", None),
    }
    return md5_sha_from_dict(cache_payload)


def chart_data_api_cache_key(
    json_body: dict[str, Any],
    cache_context: Union[int, str],
) -> str:
    """Full /chart/data response cache key: chart_data_api:{context}:{body_hash}."""
    body_hash = md5_sha_from_dict(json_body)
    return f"chart_data_api:{cache_context}:{body_hash}"
