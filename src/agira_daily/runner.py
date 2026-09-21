from __future__ import annotations

from datetime import date, datetime, time
from typing import Any, Iterable, Literal, Mapping

from .config import PipelineConfig
from .dates import processing_dates
from .db import execute_query
from .publishing import Publication, publish_batch, publish_empty
from .questions import build_question_batch
from .terminations import build_termination_batch


Feed = Literal["questions", "terminations"]


def run_feed(
    feed: Feed,
    *,
    config: PipelineConfig,
    run_date: date,
    rows: Iterable[Mapping[str, Any]] | None = None,
) -> Publication:
    dates = processing_dates(
        run_date,
        question_lag_days=config.question_lag_days,
        termination_lag_days=config.termination_lag_days,
    )
    if feed == "questions":
        source_date = dates.question_source_date
        query_path = config.question_query
        sequence = config.question_sequence
    else:
        source_date = dates.termination_source_date
        query_path = config.termination_query
        sequence = config.termination_sequence

    materialized = list(rows) if rows is not None else execute_query(
        query_path,
        target_date=source_date,
        connection_string_env=config.connection_string_env,
    )
    if not materialized:
        return publish_empty(
            feed=feed,
            run_date=run_date,
            source_date=source_date,
            history_root=config.history,
        )

    # A stable end-of-day timestamp makes retries reproducible and aligns with
    # the suggested question schedule. The date is the protocol-significant part.
    emitted_at = datetime.combine(run_date, time(23, 0))
    common = {
        "environment": config.environment,
        "account_code": config.account_code,
        "sequence": sequence,
        "emitter": config.emitter,
        "emitted_at": emitted_at,
    }
    if feed == "questions":
        batch = build_question_batch(materialized, **common)
    else:
        batch = build_termination_batch(materialized, **common)
    return publish_batch(
        batch,
        feed=feed,
        run_date=run_date,
        source_date=source_date,
        source_row_count=len(materialized),
        history_root=config.history,
        depot_root=config.depot,
    )
