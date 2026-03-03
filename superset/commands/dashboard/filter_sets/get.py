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
import json
import logging

from superset import db
from superset.commands.base import BaseCommand
from superset.key_value.models import KeyValueEntry
from superset.utils.core import get_user_id

logger = logging.getLogger(__name__)


class GetFilterSetsCommand(BaseCommand):
    def __init__(self, dashboard_id: int) -> None:
        self._dashboard_id = dashboard_id

    def run(self) -> list[dict]:
        resource_key = f"filter_set_{self._dashboard_id}"
        user_id = get_user_id()
        entry = (
            db.session.query(KeyValueEntry)
            .filter_by(resource=resource_key, created_by_fk=user_id)
            .first()
        )
        if not entry:
            return []
        try:
            data = json.loads(entry.value.decode("utf-8"))
            return data.get("sets", [])
        except (json.JSONDecodeError, AttributeError):
            logger.warning(
                "Failed to decode filter sets for dashboard %s", self._dashboard_id
            )
            return []

    def validate(self) -> None:
        pass
