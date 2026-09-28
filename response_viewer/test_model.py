from __future__ import annotations

import json

import pytest

from model import (
    contract_overview,
    criteria_summary,
    display_value,
    group_contracts,
    history_files,
    matching_contracts,
    parse_response,
    segment_code,
    summary_counts,
)


def conversation(contract: str, code: str, *, matched: bool = False) -> dict:
    return {
        "query_id": f"{contract}-20260922-000001-C{code}",
        "query_id_parts": {"numero_police": contract, "correspondence_code": code},
        "status": "matched" if matched else "no_match",
        "query": {
            "criteria": {
                "last_name_or_company_name": "MARTIN",
                "driving_licence_date": {"iso": "2020-01-02"},
            }
        },
        "records": (
            [{"contract": {"contract_number": "RETURNED-42"}}] if matched else []
        ),
    }


def test_parse_and_group_response() -> None:
    payload = json.dumps(
        {"conversations": [conversation("POL-2", "07"), conversation("POL-2", "01", matched=True)]}
    ).encode()

    grouped = group_contracts(parse_response(payload))

    assert list(grouped) == ["POL-2"]
    assert [segment_code(item) for item in grouped["POL-2"]] == ["C01", "C07"]
    assert summary_counts(grouped) == {
        "contracts": 1,
        "segments": 2,
        "matched": 1,
        "no_match": 1,
        "records": 1,
    }
    assert contract_overview(grouped)[0]["Returned contract(s)"] == "RETURNED-42"


def test_criteria_and_dates_are_human_readable() -> None:
    item = conversation("POL-1", "03")
    assert criteria_summary(item) == "Name / company: MARTIN · Licence date: 2020-01-02"
    assert display_value({"year": 2020, "month": 3, "day": None}) == "2020-03"
    assert display_value(None) == "—"


def test_invalid_document_has_clear_error() -> None:
    with pytest.raises(ValueError, match="conversations"):
        parse_response(b'{"summary": {}}')


def test_numero_police_filter_is_case_insensitive_substring() -> None:
    grouped = group_contracts(
        {"conversations": [conversation("AXS002072", "01"), conversation("PGA4015160", "01")]}
    )
    assert matching_contracts(grouped, " axs0020 ") == ["AXS002072"]
    assert matching_contracts(grouped, "") == ["AXS002072", "PGA4015160"]
    assert matching_contracts(grouped, "NOPE") == []


def test_history_files_newest_day_first(tmp_path) -> None:
    for day, name in [("2026-09-22", "a.json"), ("2026-09-26", "b.json"), ("2026-09-26", "c.EDI")]:
        (tmp_path / day).mkdir(exist_ok=True)
        (tmp_path / day / name).write_text("{}")
    assert [path.name for path in history_files(tmp_path)] == ["b.json", "a.json"]
