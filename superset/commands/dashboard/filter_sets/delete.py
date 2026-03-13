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
from datetime import datetime

from superset import db
from superset.commands.base import BaseCommand
from superset.key_value.models import KeyValueEntry
from superset.utils.core import get_user_id

logger = logging.getLogger(__name__)


class DeleteFilterSetCommand(BaseCommand):
    def __init__(self, dashboard_id: int, set_id: str) -> None:
        self._dashboard_id = dashboard_id
        self._set_id = set_id

    def run(self) -> None:
        resource_key = f"filter_set_{self._dashboard_id}"
        user_id = get_user_id()
        entry = (
            db.session.query(KeyValueEntry)
            .filter_by(resource=resource_key, created_by_fk=user_id)
            .first()
        )
        if not entry:
            raise ValueError(f"No filter sets found for dashboard {self._dashboard_id}")

        try:
            data = json.loads(entry.value.decode("utf-8"))
        except (json.JSONDecodeError, AttributeError) as ex:
            raise ValueError("Failed to decode filter sets") from ex

        sets = data.get("sets", [])
        original_count = len(sets)
        sets = [fs for fs in sets if fs.get("id") != self._set_id]

        if len(sets) == original_count:
            raise ValueError(f"Filter set {self._set_id} not found")

        if not sets:
            db.session.delete(entry)
        else:
            data["sets"] = sets
            entry.value = json.dumps(data).encode("utf-8")
            entry.changed_on = datetime.now()
            entry.changed_by_fk = user_id

        db.session.commit()

    def validate(self) -> None:
        pass
