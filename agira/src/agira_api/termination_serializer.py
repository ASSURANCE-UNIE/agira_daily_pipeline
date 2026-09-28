from __future__ import annotations

import hashlib
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import datetime

from .fixed_width import an, ddmmyyyy, digits, normalize_text, safe_filename
from .models import (
    Emitter,
    TerminationBatch,
    TerminationClaim,
    TerminationContract,
    TerminationPerson,
    TerminationRecord,
    TerminationVehicle,
)
from .serializer import APPLICATION_CODES, STM_WIDTH, build_ste


MESSAGE_CODES = {
    "create": "AGRESC",
    "modify": "AGRESM",
    "delete": "AGRESS",
}


@dataclass(frozen=True, slots=True)
class SerializedTerminationBatch:
    batch_id: str
    filename: str
    application_code: str
    payload: bytes
    sha256: str
    company_record_ids: list[str | None]
    operation_counts: dict[str, int]


def _company_identity(company: Emitter, *, encoding: str) -> str:
    return (
        digits(company.country_code, 3, required=True)
        + an(company.company_code, 6, encoding=encoding)
        + an(company.internal_company_code, 5, encoding=encoding)
    )


def _record_identification(
    record: TerminationRecord,
    *,
    encoding: str,
) -> str:
    record_id = normalize_text(record.company_record_id)
    rendered_record_id = (
        record_id.zfill(40)
        if record_id.isdigit()
        else an(record_id, 40, encoding=encoding)
    )
    return (
        "000"
        + _company_identity(record.record_company, encoding=encoding)
        + rendered_record_id
    )


def _contract(contract: TerminationContract, *, encoding: str) -> str:
    return (
        "001"
        + _company_identity(contract.insurer, encoding=encoding)
        + an(contract.contract_number, 20, encoding=encoding)
        + ddmmyyyy(contract.effective_date)
        + an(contract.bonus_malus_coefficient, 4, encoding=encoding)
    )


def _person(person: TerminationPerson, *, encoding: str) -> str:
    address_lines = list(person.address_lines) + [None] * (4 - len(person.address_lines))
    return (
        "002"
        + {"subscriber": "S", "driver": "C"}[person.role]
        + an(person.name_or_company_name, 20, encoding=encoding)
        + an(person.first_name, 12, encoding=encoding)
        + ("1" if person.person_kind == "legal_entity" else " ")
        + ddmmyyyy(person.birth_date)
        + "".join(an(line, 32, encoding=encoding) for line in address_lines)
        + an(person.postal_code, 5, encoding=encoding)
        + an(person.city, 26, encoding=encoding)
        + digits(person.siren, 9)
        + an(person.licence_issue_postal_code, 5, encoding=encoding)
        + an(person.driving_licence_number, 12, encoding=encoding)
        + ddmmyyyy(person.driving_licence_date)
    )


def _termination(record: TerminationRecord) -> str:
    assert record.termination is not None
    return (
        "003"
        + record.termination.reason_code
        + ddmmyyyy(record.termination.termination_date)
    )


def _claim(claim: TerminationClaim, *, encoding: str) -> str:
    return (
        "004"
        + an(claim.claim_number, 20, encoding=encoding)
        + claim.nature_code
        + ddmmyyyy(claim.claim_date)
        + claim.guarantee_code
        + digits(claim.responsibility_percent, 3, required=True, zero_pad=True)
        + an(claim.driver_last_name, 20, encoding=encoding)
        + an(claim.driver_first_name, 12, encoding=encoding)
    )


def _vehicle(vehicle: TerminationVehicle, *, encoding: str) -> str:
    return (
        "005"
        + vehicle.category_code
        + an(vehicle.registration_number, 12, encoding=encoding)
        + an(vehicle.manufacturer_code, 3, encoding=encoding)
        + an(vehicle.type_mine, 6, encoding=encoding)
        + an(vehicle.serial_number, 8, encoding=encoding)
    )


def _cnil(comment: str, *, encoding: str) -> str:
    return "007" + an(comment, 160, encoding=encoding)


def _stm(message_code: str, message_length: int) -> str:
    segment = (
        "STM"
        + message_code
        + "00"
        + "T"
        + digits(message_length, 5, required=True, zero_pad=True)
        + (" " * 25)
    )
    assert len(segment) == STM_WIDTH
    return segment


def serialize_termination_record(
    record: TerminationRecord,
    emitter: Emitter,
    emitted_at: datetime,
    *,
    encoding: str = "windows-1252",
    max_line_bytes: int = 8136,
) -> bytes:
    message_code = MESSAGE_CODES[record.operation]
    parts = [
        build_ste(emitter, emitted_at, encoding=encoding),
        _record_identification(record, encoding=encoding),
    ]
    if record.operation != "delete":
        assert record.contract is not None
        assert record.termination is not None
        assert record.vehicle is not None
        parts.append(_contract(record.contract, encoding=encoding))
        parts.extend(_person(person, encoding=encoding) for person in record.persons)
        parts.append(_termination(record))
        parts.extend(_claim(claim, encoding=encoding) for claim in record.claims)
        parts.append(_vehicle(record.vehicle, encoding=encoding))
        if record.cnil_comment:
            parts.append(_cnil(record.cnil_comment, encoding=encoding))
    tail = "".join(parts)
    message_length = STM_WIDTH + len(tail.encode(encoding))
    payload = (_stm(message_code, message_length) + tail).encode(encoding)
    if len(payload) != message_length:
        raise AssertionError("rendered message does not match declared STM length")
    if len(payload) > max_line_bytes:
        raise ValueError(
            f"message is {len(payload)} bytes; AGIRA maximum is {max_line_bytes}"
        )
    return payload


def _default_filename(batch: TerminationBatch, emitted_at: datetime) -> str:
    application_code = APPLICATION_CODES[batch.environment]
    return (
        f"RA-{batch.account_code}-{application_code}."
        f"{batch.account_code}_{emitted_at:%Y%m%d}{batch.sequence:04d}.TXT"
    )


def serialize_termination_batch(
    batch: TerminationBatch,
    *,
    encoding: str = "windows-1252",
    max_line_bytes: int = 8136,
) -> SerializedTerminationBatch:
    emitted_at = batch.emitted_at or datetime.now().astimezone().replace(tzinfo=None)
    lines = [
        serialize_termination_record(
            record,
            batch.emitter,
            emitted_at,
            encoding=encoding,
            max_line_bytes=max_line_bytes,
        )
        for record in batch.records
    ]
    payload = b"\r\n".join(lines) + b"\r\n"
    filename = safe_filename(batch.output_filename or _default_filename(batch, emitted_at))
    return SerializedTerminationBatch(
        batch_id=str(uuid.uuid4()),
        filename=filename,
        application_code=APPLICATION_CODES[batch.environment],
        payload=payload,
        sha256=hashlib.sha256(payload).hexdigest(),
        company_record_ids=[record.company_record_id for record in batch.records],
        operation_counts=dict(Counter(record.operation for record in batch.records)),
    )
