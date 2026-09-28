import json
from datetime import datetime
from pathlib import Path

import pytest

from agira_api import json_to_agira
from agira_daily.inbound import archive_inbound_file, discover_inbound_files


def _question_payload() -> bytes:
    rendered = json_to_agira(
        {
            "environment": "test",
            "account_code": "AC000189",
            "sequence": 1,
            "emitted_at": datetime(2026, 9, 21, 18, 0).isoformat(),
            "emitter": {
                "country_code": "250",
                "company_code": "0703",
                "internal_company_code": "ASUNI",
            },
            "questions": [
                {
                    "query_id": "POL-1-20260921-000001-C07",
                    "criteria": {"siren": "123456789"},
                }
            ],
        }
    )
    return rendered.payload


def _termination_payload() -> bytes:
    rendered = json_to_agira(
        {
            "environment": "test",
            "account_code": "AC000189",
            "sequence": 2,
            "emitted_at": datetime(2026, 9, 21, 18, 0).isoformat(),
            "emitter": {
                "country_code": "250",
                "company_code": "0703",
                "internal_company_code": "ASUNI",
            },
            "records": [
                {
                    "operation": "delete",
                    "company_record_id": "RECORD-1",
                    "record_company": {
                        "country_code": "250",
                        "company_code": "0703",
                        "internal_company_code": "ASUNI",
                    },
                }
            ],
        }
    )
    return rendered.payload


def _rejected(payload: bytes) -> bytes:
    line = bytearray(payload.rstrip(b"\r\n"))
    error = ("STR" + "00004" + "STM" + "STRUCTURE ERRONEE").ljust(41).encode(
        "windows-1252"
    )
    rejected = line + error
    rejected[12:17] = f"{len(rejected):05d}".encode("ascii")
    return bytes(rejected) + b"\r\n"


def test_archives_swapped_response_and_rejection_idempotently(tmp_path: Path) -> None:
    depot = tmp_path / "data/depot"
    history = tmp_path / "data/history"
    response = (
        depot
        / "interrogations/rej"
        / "AC000189-CSHOFR43.AC000189_20260922012938955_REP.EDI"
    )
    rejection = (
        depot
        / "interrogations/resp"
        / "AC000189-CSHRFR43.AC000189_20260922012922559_REJ.EDI"
    )
    response.parent.mkdir(parents=True)
    rejection.parent.mkdir(parents=True)
    response.write_bytes(_question_payload())
    rejection.write_bytes(_rejected(_question_payload()))

    sources = discover_inbound_files(depot)
    results = [
        archive_inbound_file(source, history_root=history) for source in sources
    ]

    assert {result.category for result in results} == {"rej", "resp"}
    assert {result.status for result in results} == {"archived"}
    assert all(result.source_deleted for result in results)
    assert not response.exists()
    assert not rejection.exists()
    response_json = json.loads(
        (
            history
            / "interrogations/resp/2026-09-22"
            / response.with_suffix(".json").name
        ).read_text(encoding="utf-8")
    )
    rejection_json = json.loads(
        (
            history
            / "interrogations/rej/2026-09-22"
            / rejection.with_suffix(".json").name
        ).read_text(encoding="utf-8")
    )
    assert response_json["summary"]["statuses"] == {"no_match": 1}
    assert rejection_json["summary"]["statuses"] == {"rejected": 1}

    response.write_bytes(_question_payload())
    rejection.write_bytes(_rejected(_question_payload()))
    repeated = [
        archive_inbound_file(source, history_root=history)
        for source in (response, rejection)
    ]
    assert {result.status for result in repeated} == {"already_archived"}
    assert not response.exists()
    assert not rejection.exists()


def test_archives_mixed_question_and_termination_rejections(tmp_path: Path) -> None:
    source = (
        tmp_path
        / "data/depot/interrogations/rej"
        / "AC000189-CSHRFR43.AC000189_20260922012922559_REJ.EDI"
    )
    source.parent.mkdir(parents=True)
    source.write_bytes(
        _rejected(_question_payload()) + _rejected(_termination_payload())
    )

    result = archive_inbound_file(
        source,
        history_root=tmp_path / "data/history",
    )
    translated = json.loads(result.json_path.read_text(encoding="utf-8"))

    assert translated["document_type"] == "agira_mixed_result_file"
    assert translated["summary"]["line_count"] == 2
    assert translated["question_results"]["summary"]["statuses"] == {
        "rejected": 1
    }
    assert translated["termination_results"]["summary"]["rejected_count"] == 1
    assert not source.exists()


def test_refuses_to_overwrite_changed_history_json(tmp_path: Path) -> None:
    source = (
        tmp_path
        / "data/depot/interrogations/resp"
        / "AC000189-CSHOFR43.AC000189_20260922012938955_REP.EDI"
    )
    source.parent.mkdir(parents=True)
    source.write_bytes(_question_payload())
    history = tmp_path / "data/history"
    result = archive_inbound_file(source, history_root=history)
    result.json_path.write_text("{}\n", encoding="utf-8")
    source.write_bytes(_question_payload())

    with pytest.raises(FileExistsError, match="contains different JSON"):
        archive_inbound_file(source, history_root=history)
    assert source.exists()


def test_requires_a_reception_date_in_filename(tmp_path: Path) -> None:
    source = tmp_path / "data/depot/interrogations/resp/RESULT_REP.EDI"
    source.parent.mkdir(parents=True)
    source.write_bytes(_question_payload())

    with pytest.raises(ValueError, match="cannot determine reception date"):
        archive_inbound_file(source, history_root=tmp_path / "data/history")
