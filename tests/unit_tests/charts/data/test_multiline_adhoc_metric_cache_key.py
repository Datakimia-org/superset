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
"""Orderby adhoc SQL must not change the dataframe cache key.

Table charts copy the first metric into ``orderby``. After JSON those are
distinct dicts. ``get_sqla_query`` sanitizes ``orderby[].sqlExpression`` with
sqlglot while building SQL. That rewrite has to stay off the query form: the
dataframe is stored under the key hashed before SQL generation, and
``data_from_cache`` rehashes the form persisted afterwards.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any

import pytest
from pytest_mock import MockerFixture
from sqlalchemy import create_engine
from sqlalchemy.orm.session import Session
from sqlalchemy.pool import StaticPool

from superset.common.query_object import QueryObject
from superset.models.helpers import SQLA_QUERY_KEYS
from superset.superset_typing import AdhocMetric


@pytest.fixture
def database(mocker: MockerFixture, session: Session) -> Any:
    from superset.connectors.sqla.models import SqlaTable
    from superset.models.core import Database

    SqlaTable.metadata.create_all(session.get_bind())

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    database = Database(database_name="db", sqlalchemy_uri="sqlite://")

    connection = engine.raw_connection()
    connection.execute("CREATE TABLE t (a INTEGER)")
    connection.commit()

    @contextmanager
    def mock_get_sqla_engine(
        catalog: str | None = None,
        schema: str | None = None,
        **kwargs: Any,
    ) -> Any:
        yield engine

    mocker.patch.object(database, "get_sqla_engine", new=mock_get_sqla_engine)
    return database


def _adhoc_count(sql_expression: str) -> AdhocMetric:
    return {
        "expressionType": "SQL",
        "sqlExpression": sql_expression,
        "label": "COUNT(*)",
    }


@pytest.mark.parametrize(
    "sql_expression",
    [
        "COUNT(*)",
        "COUNT(\r\n  *\r\n)",
        "COUNT(\n  *\n)",
    ],
)
def test_orderby_adhoc_sql_keeps_dataframe_cache_key(
    database: Any,
    sql_expression: str,
) -> None:
    """Sanitizing orderby SQL must not change the key hashed from the form."""
    from superset.connectors.sqla.models import SqlaTable, TableColumn

    metric = _adhoc_count(sql_expression)
    # Distinct dict, same SQL: what the chart/data body looks like after JSON.
    orderby_metric = _adhoc_count(sql_expression)
    assert orderby_metric is not metric

    table = SqlaTable(
        id=1,
        database=database,
        schema=None,
        table_name="t",
        columns=[TableColumn(column_name="a", type="INTEGER")],
    )
    query_object = QueryObject(
        datasource=table,
        columns=["a"],
        metrics=[metric],
        orderby=[(orderby_metric, False)],
        is_timeseries=False,
    )

    key_before = query_object.cache_key()
    filtered = {
        key: value
        for key, value in query_object.to_dict().items()
        if key in SQLA_QUERY_KEYS
    }
    sqla_query = table.get_sqla_query(**filtered)
    key_after = query_object.cache_key()

    assert metric["sqlExpression"] == sql_expression
    assert orderby_metric["sqlExpression"] == sql_expression, (
        "orderby sqlExpression was rewritten in place to "
        f"{orderby_metric['sqlExpression']!r}; the qc- form would hash to a "
        "different dataframe key than the one stored before SQL generation"
    )
    assert key_before == key_after

    with database.get_sqla_engine() as engine:
        sql = str(
            sqla_query.sqla_query.compile(
                dialect=engine.dialect,
                compile_kwargs={"literal_binds": True},
            )
        )
    assert "COUNT(*)" in sql
    assert "\r" not in sql
