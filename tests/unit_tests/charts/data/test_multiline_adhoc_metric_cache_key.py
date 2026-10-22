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
"""Async chart-data cache key vs persisted query-context form.

Table charts put the first adhoc metric into ``orderby`` (same SQL, separate
dict after JSON). ``ExploreMixin.get_sqla_query`` sanitizes that expression via
``_process_orderby_expression`` / ``sanitize_clause`` after
``QueryObject.cache_key`` is hashed. The rewrite must run on a copy: the same
dict is stored in the ``qc-`` form, and ``data_from_cache`` rehashes it.
"""

from __future__ import annotations

import pickle
from contextlib import contextmanager
from datetime import timedelta
from typing import Any, Iterator
from unittest.mock import MagicMock

import pandas as pd

from superset.common.chart_data import ChartDataResultFormat, ChartDataResultType
from superset.common.db_query_status import QueryStatus
from superset.common.query_context import QueryContext
from superset.common.query_object import QueryObject
from superset.db_engine_specs.bigquery import BigQueryEngineSpec
from superset.models.helpers import ExploreMixin, QueryResult
from superset.utils import json

# Chart 619 metric, as stored in the DB (CRLF from the SQL editor).
_MULTILINE_SQL = (
    " CONCAT(\r\n"
    "    FORMAT_DATE('%m/%d/%Y', MIN(`data_date`)),\r\n"
    "    ' - ',\r\n"
    "    FORMAT_DATE('%m/%d/%Y', MAX(`data_date`))\r\n"
    "  ) "
)

# Same expression after sqlglot generate(pretty=False). Already canonical,
# so the orderby rewrite is a no-op and both cache keys match.
_SINGLE_LINE_SQL = (
    "CONCAT(FORMAT_DATE('%m/%d/%Y', MIN(`data_date`)), "
    "' - ', FORMAT_DATE('%m/%d/%Y', MAX(`data_date`)))"
)


class _StoppedAfterOrderByError(Exception):
    """Raised once ``get_sqla_query`` has passed the orderby rewrite."""


@contextmanager
def _engine() -> Iterator[MagicMock]:
    yield MagicMock()


class _Datasource(ExploreMixin):
    """Runs the real ``get_sqla_query`` orderby rewrite, then stops."""

    database_id = 1
    catalog = None
    sql = None
    uid = "75__table"
    cache_timeout = 300
    changed_on = None
    is_rls_supported = False
    verbose_map: dict[str, str] = {}
    data: dict[str, Any] = {}

    def __init__(self) -> None:
        self._database = type(
            "Database",
            (),
            {"backend": "bigquery", "get_sqla_engine": staticmethod(_engine)},
        )()

    @property
    def database(self) -> Any:  # type: ignore[override]
        return self._database

    @property
    def schema(self) -> str:  # type: ignore[override]
        return "public"

    @property
    def columns(self) -> list[Any]:  # type: ignore[override]
        return []

    @property
    def metrics(self) -> list[Any]:  # type: ignore[override]
        return []

    @property
    def column_names(self) -> list[str]:
        return []

    @property
    def dttm_cols(self) -> list[str]:
        return []

    @property
    def main_dttm_col(self) -> None:
        return None

    @property
    def db_engine_spec(self) -> type[BigQueryEngineSpec]:  # type: ignore[override]
        return BigQueryEngineSpec

    def get_template_processor(self, **kwargs: Any) -> None:  # type: ignore[override]
        return None

    def get_extra_cache_keys(self, query_obj: dict[str, Any]) -> list[Any]:
        return []

    def get_from_clause(self, template_processor: Any = None) -> tuple[Any, Any]:
        raise _StoppedAfterOrderByError()

    def get_query_result(self, query_object: QueryObject) -> QueryResult:
        # Production path: query() -> get_query_str_extended() -> get_sqla_query(),
        # which sanitizes orderby sqlExpression before the SELECT is built.
        try:
            self.get_sqla_query(
                columns=list(query_object.columns),
                extras=query_object.extras,
                filter=query_object.filter,
                granularity=query_object.granularity,
                is_timeseries=bool(query_object.is_timeseries),
                metrics=query_object.metrics,
                orderby=query_object.orderby,
                order_desc=query_object.order_desc,
                row_limit=query_object.row_limit,
                row_offset=query_object.row_offset,
            )
        except _StoppedAfterOrderByError:
            pass
        return QueryResult(
            df=pd.DataFrame({"Date": ["01/01/2024 - 01/31/2024"]}),
            query="SELECT 1",
            duration=timedelta(0),
            status=QueryStatus.SUCCESS,
        )


def _metric(sql_expression: str) -> dict[str, Any]:
    return {
        "expressionType": "SQL",
        "sqlExpression": sql_expression,
        "label": "Date",
        "hasCustomLabel": True,
        "optionName": "metric_r0f70wp0apa_yjvt69rk2u",
    }


def _request_query(sql_expression: str) -> dict[str, Any]:
    """POST body fragment after ``request.json`` / Celery JSON (copies, not refs)."""
    metric = _metric(sql_expression)
    # Table aggregate mode: orderby = [[metrics[0], false]] before stringify.
    payload = {"metrics": [metric], "orderby": [[metric, False]], "columns": []}
    return json.loads(json.dumps(payload))


def _async_cache_keys(sql_expression: str) -> tuple[str, str, dict[str, Any]]:
    """
    Worker dataframe key, then the key ``data_from_cache`` recomputes.

    The second key is hashed from the query dict ``get_payload`` stores in the
    ``qc-`` cache value, after a pickle round-trip (RedisCache default codec).
    """
    datasource = _Datasource()
    request_query = _request_query(sql_expression)
    query_object = QueryObject(
        datasource=datasource,  # type: ignore[arg-type]
        metrics=request_query["metrics"],
        orderby=request_query["orderby"],
        columns=[],
        extras={},
        row_limit=1000,
        is_timeseries=False,
    )
    query_context = QueryContext(
        datasource=datasource,  # type: ignore[arg-type]
        queries=[query_object],
        slice_=None,
        form_data={"slice_id": 619, "viz_type": "table"},
        result_type=ChartDataResultType.FULL,
        result_format=ChartDataResultFormat.JSON,
        cache_values={
            "datasource": {"id": 75, "type": "table"},
            "queries": [request_query],
            "result_type": ChartDataResultType.FULL,
            "result_format": ChartDataResultFormat.JSON,
        },
    )

    payload = query_context.get_payload(cache_query_context=True)
    worker_key = payload["queries"][0]["cache_key"]

    # What set_and_log_cache writes under the qc- key, as Redis would return it.
    # RedisCache pickles the qc- value. Round-trip our own object, not external data.
    stored_query = pickle.loads(  # noqa: S301
        pickle.dumps(query_context.cache_values["queries"][0])
    )
    reloaded = QueryObject(
        datasource=datasource,  # type: ignore[arg-type]
        metrics=stored_query["metrics"],
        orderby=stored_query["orderby"],
        columns=[],
        extras={},
        row_limit=1000,
        is_timeseries=False,
    )
    get_key = query_context.query_cache_key(reloaded)
    return worker_key, get_key, stored_query


def test_multiline_adhoc_sql_cache_key_stable_after_async_round_trip() -> None:
    worker_key, get_key, stored = _async_cache_keys(_MULTILINE_SQL)
    orderby_sql = stored["orderby"][0][0]["sqlExpression"]
    metrics_sql = stored["metrics"][0]["sqlExpression"]
    assert worker_key == get_key, (
        "dataframe cache key hashed before get_sqla_query does not match the key "
        "data_from_cache recomputes from the persisted qc- form\n"
        f"worker={worker_key}\n"
        f"get={get_key}\n"
        f"stored metrics sql={metrics_sql!r}\n"
        f"stored orderby sql={orderby_sql!r}"
    )


def test_single_line_adhoc_sql_metric_cache_key_is_stable() -> None:
    worker_key, get_key, stored = _async_cache_keys(_SINGLE_LINE_SQL)
    assert stored["orderby"][0][0]["sqlExpression"] == _SINGLE_LINE_SQL
    assert worker_key == get_key
