from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import Any


TARGET_DATE_PARAMETER = ":target_date"


def parameterize_query(sql: str, target_date: date) -> tuple[str, tuple[date, ...]]:
    count = sql.count(TARGET_DATE_PARAMETER)
    if count == 0:
        raise ValueError(
            f"SQL query must contain at least one {TARGET_DATE_PARAMETER} parameter"
        )
    return sql.replace(TARGET_DATE_PARAMETER, "?"), (target_date,) * count


def execute_query(
    query_path: Path,
    *,
    target_date: date,
    connection_string_env: str,
) -> list[dict[str, Any]]:
    """Execute one read query through pyodbc and return lower-case column mappings."""

    try:
        import pyodbc
    except ImportError as exc:
        raise RuntimeError(
            "database support is not installed; run `uv sync --extra database`"
        ) from exc
    if not query_path.is_file():
        raise FileNotFoundError(
            f"missing SQL query {query_path}; copy the example to query.sql"
        )
    connection_string = os.getenv(connection_string_env)
    if not connection_string:
        raise RuntimeError(f"environment variable {connection_string_env} is not set")
    sql, parameters = parameterize_query(
        query_path.read_text(encoding="utf-8"), target_date
    )
    with pyodbc.connect(connection_string) as connection:
        cursor = connection.cursor()
        cursor.execute(sql, *parameters)
        if cursor.description is None:
            raise ValueError("SQL query did not return a result set")
        columns = [str(item[0]).strip().lower() for item in cursor.description]
        if len(columns) != len(set(columns)):
            raise ValueError("SQL query returned duplicate column aliases")
        return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]
