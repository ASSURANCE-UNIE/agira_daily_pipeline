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
    # psycopg reads every % as a placeholder, so literal ones (LIKE 'RC%') double up.
    sql = sql.replace("%", "%%").replace(TARGET_DATE_PARAMETER, "%s")
    return sql, (target_date,) * count


def connection_string(env_name: str, env_file: Path = Path("prd.env")) -> str:
    """Environment variable first, then a KEY=value line in prd.env."""

    value = os.getenv(env_name)
    if not value and env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            key, _, raw = line.partition("=")
            if key.strip() == env_name:
                value = raw.strip().strip("'\"")
    if not value:
        raise RuntimeError(f"{env_name} is not set (environment or {env_file})")
    # SQLAlchemy-style URLs carry a driver suffix psycopg does not understand.
    return value.replace("postgresql+psycopg2://", "postgresql://", 1)


def execute_query(
    query_path: Path,
    *,
    target_date: date,
    connection_string_env: str,
) -> list[dict[str, Any]]:
    """Execute one read query through psycopg and return lower-case column mappings."""

    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError(
            "database support is not installed; run `uv sync --extra database`"
        ) from exc
    if not query_path.is_file():
        raise FileNotFoundError(f"missing SQL query {query_path}")
    sql, parameters = parameterize_query(
        query_path.read_text(encoding="utf-8"), target_date
    )
    with psycopg.connect(connection_string(connection_string_env)) as connection:
        connection.read_only = True
        cursor = connection.execute(sql, parameters)
        if cursor.description is None:
            raise ValueError("SQL query did not return a result set")
        columns = [str(item.name).strip().lower() for item in cursor.description]
        if len(columns) != len(set(columns)):
            raise ValueError("SQL query returned duplicate column aliases")
        return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]
