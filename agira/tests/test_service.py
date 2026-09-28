from datetime import datetime

import pytest

from agira_api import agira_to_json, json_to_agira


def _document() -> dict:
    return {
        "environment": "test",
        "account_code": "AC000189",
        "sequence": 7,
        "emitted_at": datetime(2026, 9, 18, 18, 0).isoformat(),
        "emitter": {
            "country_code": "250",
            "company_code": "0703",
            "internal_company_code": "ASUNI",
        },
        "questions": [
            {
                "query_id": "QUESTION-1",
                "criteria": {"siren": "123456789"},
            }
        ],
    }


def test_library_round_trip() -> None:
    rendered = json_to_agira(_document())
    translated = agira_to_json(
        rendered.payload,
        source_filename=rendered.filename,
        kind="questions",
    )

    assert rendered.document_type == "questions"
    assert rendered.item_count == 1
    assert translated["questions"][0]["criteria"]["siren"] == "123456789"


def test_library_requires_exactly_one_document_discriminator() -> None:
    with pytest.raises(ValueError, match="exactly one discriminator"):
        json_to_agira({"environment": "test"})
