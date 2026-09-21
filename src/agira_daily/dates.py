from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True, slots=True)
class ProcessingDates:
    run_date: date
    question_source_date: date
    termination_source_date: date


def processing_dates(
    run_date: date,
    *,
    question_lag_days: int = 1,
    termination_lag_days: int = 35,
) -> ProcessingDates:
    if question_lag_days not in {0, 1}:
        raise ValueError("question_lag_days must be 0 (end of day) or 1 (next day)")
    if termination_lag_days < 0:
        raise ValueError("termination_lag_days cannot be negative")
    return ProcessingDates(
        run_date=run_date,
        question_source_date=run_date - timedelta(days=question_lag_days),
        termination_source_date=run_date - timedelta(days=termination_lag_days),
    )
