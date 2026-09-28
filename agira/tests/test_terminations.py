from copy import deepcopy
from datetime import datetime

import pytest
from pydantic import ValidationError

from agira_api.models import TerminationBatch
from agira_api.parser import parse_reply_bytes
from agira_api.termination_serializer import serialize_termination_batch
from agira_api.translators import (
    translate_termination_request_bytes,
    translate_termination_response_bytes,
)


def _payload(*, reason_code: str = "5") -> dict:
    return {
        "environment": "test",
        "account_code": "AC000189",
        "sequence": 41,
        "emitted_at": datetime(2026, 9, 11, 15, 0, 0).isoformat(),
        "output_filename": "TERMINATIONS-TEST.TXT",
        "emitter": {
            "country_code": "250",
            "company_code": "0703",
            "internal_company_code": "ASUNI",
        },
        "records": [
            {
                "operation": "create",
                "company_record_id": "AXA-RESIL-000001",
                "record_company": {
                    "country_code": "250",
                    "company_code": "0200",
                    "internal_company_code": "",
                },
                "contract": {
                    "insurer": {
                        "country_code": "250",
                        "company_code": "0200",
                        "internal_company_code": "ALLIA",
                    },
                    "contract_number": "POLICY-12345",
                    "effective_date": "2024-01-01",
                    "bonus_malus_coefficient": "1,00",
                },
                "persons": [
                    {
                        "role": "subscriber",
                        "person_kind": "natural_person",
                        "name_or_company_name": "DUPONT",
                        "first_name": "ALICE",
                        "birth_date": "1990-05-12",
                        "address_lines": ["10 RUE EXEMPLE"],
                        "postal_code": "75001",
                        "city": "PARIS",
                        "driving_licence_number": "LICENCE-1",
                        "driving_licence_date": "2008-07-16",
                    }
                ],
                "termination": {
                    "reason_code": reason_code,
                    "termination_date": "2026-09-30",
                },
                "claims": [],
                "vehicle": {
                    "category_code": "0",
                    "registration_number": "AB-123-CD",
                    "manufacturer_code": "XXX",
                    "type_mine": "TYPE01",
                    "serial_number": "SERIAL01",
                },
            }
        ],
    }


def test_serializes_and_translates_complete_termination_record() -> None:
    batch = TerminationBatch.model_validate(_payload())
    rendered = serialize_termination_batch(batch)
    line = rendered.payload.splitlines()[0]

    assert line.startswith(b"STMAGRESC")
    assert int(line[12:17]) == len(line)
    parsed = parse_reply_bytes(rendered.payload, source_filename=rendered.filename)
    record = parsed["messages"][0]["record"]
    assert record["contract"]["contract_number"] == "POLICY-12345"
    assert record["termination"]["reason_code"] == "5"
    assert record["vehicle"]["registration_number"] == "AB-123-CD"

    translated = translate_termination_request_bytes(
        rendered.payload,
        source_filename=rendered.filename,
    )
    assert translated["summary"]["is_valid"] is True
    assert translated["records"][0]["status"] == "ready_to_send"
    assert translated["records"][0]["record"]["termination"]["reason_label"]


def test_termination_response_marks_str_as_rejected() -> None:
    rendered = serialize_termination_batch(TerminationBatch.model_validate(_payload()))
    line = rendered.payload.rstrip(b"\r\n")
    error = (
        "STR"
        + "00005"
        + "003"
        + "001"
        + "0024"
        + "DATE RESILIATION INVAL."
    ).ljust(41).encode("windows-1252")
    assert len(error) == 41

    translated = translate_termination_response_bytes(
        line + error + b"\r\n",
        source_filename="TERMINATION-RESULT.TXT",
    )
    assert translated["records"][0]["status"] == "rejected"
    assert translated["records"][0]["errors"][0]["error_code"] == "00005"
    assert translated["summary"]["rejected_count"] == 1


def test_termination_response_accepts_stm_length_including_str() -> None:
    rendered = serialize_termination_batch(TerminationBatch.model_validate(_payload()))
    message = rendered.payload.rstrip(b"\r\n")
    error = ("STR" + "00004" + "STM" + "STRUCTURE ERRONEE").ljust(41).encode(
        "windows-1252"
    )
    response = bytearray(message + error)
    response[12:17] = f"{len(response):05d}".encode("ascii")

    translated = translate_termination_response_bytes(
        bytes(response) + b"\r\n",
        source_filename="AGIRA-OBSERVED-REJ.EDI",
    )

    assert translated["summary"]["record_count"] == 1
    assert translated["summary"]["rejected_count"] == 1
    assert translated["summary"]["file_error_count"] == 0
    record = translated["records"][0]
    assert record["status"] == "rejected"
    assert record["errors"] == [
        {
            "error_code": "00004",
            "segment_in_error": "STM",
            "detail": "STRUCTURE ERRONEE",
        }
    ]
    assert record["protocol"]["declared_length"] == len(response)
    assert record["protocol"]["functional_message_length"] == len(message)
    assert (
        record["protocol"]["declared_length_scope"]
        == "response_line_including_str"
    )


def test_reason_three_requires_a_claim() -> None:
    with pytest.raises(ValidationError, match="at least one claim"):
        TerminationBatch.model_validate(_payload(reason_code="3"))


def test_cnil_segment_requires_explicit_rectification_confirmation() -> None:
    payload = _payload()
    payload["records"][0]["cnil_comment"] = "COMMENTAIRE GENERIQUE"

    with pytest.raises(ValidationError, match="cnil_rectification_confirmed"):
        TerminationBatch.model_validate(payload)


def test_create_modify_delete_claim_and_cnil_are_supported() -> None:
    payload = _payload()
    create_record = payload["records"][0]
    modify_record = deepcopy(create_record)
    modify_record["operation"] = "modify"
    modify_record["termination"]["reason_code"] = "3"
    modify_record["claims"] = [
        {
            "claim_number": "CLAIM-0001",
            "nature_code": "M",
            "claim_date": "2026-06-07",
            "guarantee_code": "07",
            "responsibility_percent": 100,
            "driver_last_name": "DUPONT",
            "driver_first_name": "ALICE",
        },
        {
            "claim_number": "CLAIM-0002",
            "nature_code": "C",
            "claim_date": "2026-07-08",
            "guarantee_code": "01",
            "responsibility_percent": 0,
        },
    ]
    modify_record["persons"].append(
        {
            "role": "driver",
            "person_kind": "natural_person",
            "name_or_company_name": "MARTIN",
            "first_name": "LOUIS",
            "birth_date": "1985-03-20",
            "address_lines": ["20 AVENUE TEST"],
            "postal_code": "69001",
            "city": "LYON",
        }
    )
    modify_record["cnil_comment"] = "RECTIFICATION VALIDEE"
    modify_record["cnil_rectification_confirmed"] = True
    delete_record = {
        "operation": "delete",
        "company_record_id": "AXA-RESIL-TO-DELETE",
        "record_company": {
            "country_code": "250",
            "company_code": "0200",
            "internal_company_code": "",
        },
    }
    payload["records"] = [create_record, modify_record, delete_record]
    batch = TerminationBatch.model_validate(payload)

    rendered = serialize_termination_batch(batch)
    parsed = parse_reply_bytes(rendered.payload, source_filename=rendered.filename)

    assert rendered.operation_counts == {"create": 1, "modify": 1, "delete": 1}
    assert [message["message_type"] for message in parsed["messages"]] == [
        "AGRESC",
        "AGRESM",
        "AGRESS",
    ]
    assert parsed["messages"][1]["record"]["claims"][0]["claim_number"] == "CLAIM-0001"
    assert len(parsed["messages"][1]["record"]["claims"]) == 2
    assert len(parsed["messages"][1]["record"]["persons"]) == 2
    assert parsed["messages"][1]["record"]["cnil"]["text"] == "RECTIFICATION VALIDEE"
    assert list(parsed["messages"][2]["record"]) == ["identification"]


def test_numeric_company_record_id_uses_legacy_zero_padding_without_shifting_000() -> None:
    payload = _payload()
    payload["records"][0]["company_record_id"] = "12345"
    rendered = serialize_termination_batch(TerminationBatch.model_validate(payload))
    line = rendered.payload.splitlines()[0].decode("windows-1252")
    record_segment = line[94:151]

    assert record_segment[:3] == "000"
    assert record_segment[3:17] == "2500200       "
    assert record_segment[17:57] == "12345".zfill(40)
