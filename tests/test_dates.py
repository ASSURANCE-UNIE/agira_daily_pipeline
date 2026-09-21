from datetime import date

import pytest

from agira_daily.dates import processing_dates


def test_default_source_dates() -> None:
    dates = processing_dates(date(2026, 9, 18))
    assert dates.question_source_date == date(2026, 9, 17)
    assert dates.termination_source_date == date(2026, 8, 14)


def test_end_of_day_questions_use_run_date() -> None:
    dates = processing_dates(date(2026, 9, 18), question_lag_days=0)
    assert dates.question_source_date == date(2026, 9, 18)


def test_question_lag_is_constrained() -> None:
    with pytest.raises(ValueError, match="0 .* or 1"):
        processing_dates(date(2026, 9, 18), question_lag_days=2)
