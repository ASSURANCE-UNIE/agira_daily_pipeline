from datetime import date

import pytest

from agira_daily.db import parameterize_query


def test_target_date_is_bound_not_interpolated() -> None:
    sql, parameters = parameterize_query(
        "SELECT * FROM t WHERE d=:target_date OR amended=:target_date",
        date(2026, 9, 17),
    )
    assert sql == "SELECT * FROM t WHERE d=? OR amended=?"
    assert parameters == (date(2026, 9, 17), date(2026, 9, 17))


def test_query_must_have_target_date() -> None:
    with pytest.raises(ValueError, match=":target_date"):
        parameterize_query("SELECT * FROM t", date(2026, 9, 17))
