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
import time
import uuid
from datetime import datetime
from typing import Any

from superset import db
from superset.commands.base import BaseCommand
from superset.key_value.models import KeyValueEntry
from superset.utils.core import get_user_id

logger = logging.getLogger(__name__)

MAX_FILTER_SETS = 20


class CreateFilterSetCommand(BaseCommand):
    def __init__(
        self,
        dashboard_id: int,
        data_mask: dict[str, Any],
        applied_filters: list[dict[str, Any]],
        label: str | None = None,
    ) -> None:
        self._dashboard_id = dashboard_id
        self._data_mask = data_mask
        self._applied_filters = applied_filters
        self._label = label

    def run(self) -> str:
        resource_key = f"filter_set_{self._dashboard_id}"
        user_id = get_user_id()
        entry = (
            db.session.query(KeyValueEntry)
            .filter_by(resource=resource_key, created_by_fk=user_id)
            .first()
        )

        if entry:
            try:
                data = json.loads(entry.value.decode("utf-8"))
            except (json.JSONDecodeError, AttributeError):
                data = {"sets": []}
        else:
            data = {"sets": []}

        new_id = str(uuid.uuid4())
        new_set: dict[str, Any] = {
            "id": new_id,
            "timestamp": int(time.time() * 1000),
            "dataMask": self._data_mask,
            "appliedFilters": self._applied_filters,
        }
        if self._label:
            new_set["customLabel"] = self._label

        sets: list[dict[str, Any]] = data.get("sets", [])
        sets = [new_set] + sets
        # Enforce maximum, dropping oldest entries
        if len(sets) > MAX_FILTER_SETS:
            sets = sets[:MAX_FILTER_SETS]
        data["sets"] = sets

        encoded = json.dumps(data).encode("utf-8")
        if entry:
            entry.value = encoded
            entry.changed_on = datetime.now()
            entry.changed_by_fk = user_id
        else:
            entry = KeyValueEntry(
                resource=resource_key,
                value=encoded,
                created_on=datetime.now(),
                created_by_fk=user_id,
            )
            db.session.add(entry)

        db.session.commit()
        return new_id

    def validate(self) -> None:
        pass
