from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime

from .fixed_width import an, ddmmyyyy, digits, safe_filename, yyyymmddhhmmss
from .models import Emitter, Question, QuestionBatch


STM_WIDTH = 42
STE_WIDTH = 52
Q00_WIDTH = 69
Q01_WIDTH = 123
QUESTION_MESSAGE_WIDTH = STM_WIDTH + STE_WIDTH + Q00_WIDTH + Q01_WIDTH

APPLICATION_CODES = {
    "test": "HOCSFR43",
    "production": "HOCSFR42",
}


@dataclass(frozen=True, slots=True)
class SerializedBatch:
    batch_id: str
    filename: str
    application_code: str
    payload: bytes
    sha256: str
    query_ids: list[str]


def _company_identity(emitter: Emitter, *, encoding: str) -> str:
    return (
        digits(emitter.country_code, 3, required=True)
        + an(emitter.company_code, 6, encoding=encoding)
        + an(emitter.internal_company_code, 5, encoding=encoding)
    )


def build_ste(emitter: Emitter, emitted_at: datetime, *, encoding: str) -> str:
    segment = (
        "STE"
        + "C"
        + _company_identity(emitter, encoding=encoding)
        + (" " * 3)
        + yyyymmddhhmmss(emitted_at)
        + "T"
        + (" " * 16)
    )
    assert len(segment.encode(encoding)) == STE_WIDTH
    return segment


def build_q00(emitter: Emitter, question: Question, *, encoding: str) -> str:
    segment = (
        "Q00"
        + _company_identity(emitter, encoding=encoding)
        + an(question.query_id, 40, encoding=encoding)
        + (" " * 12)
    )
    assert len(segment.encode(encoding)) == Q00_WIDTH
    return segment


def build_q01(question: Question, *, encoding: str) -> str:
    criteria = question.criteria
    segment = (
        "Q01"
        + an(criteria.previous_insurer_company_code, 6, encoding=encoding)
        + an(criteria.contract_number, 20, encoding=encoding)
        + an(criteria.last_name_or_company_name, 20, encoding=encoding)
        + an(criteria.birth_or_maiden_name, 20, encoding=encoding)
        + an(criteria.first_name, 12, encoding=encoding)
        + ddmmyyyy(criteria.birth_date)
        + an(criteria.residence_postal_code, 5, encoding=encoding)
        + ddmmyyyy(criteria.driving_licence_date)
        + an(criteria.registration_number, 12, encoding=encoding)
        + digits(criteria.siren, 9)
    )
    assert len(segment.encode(encoding)) == Q01_WIDTH
    return segment


def build_stm(message_length: int, *, encoding: str) -> str:
    segment = (
        "STM"
        + "AGQUES"
        + "00"
        + "T"
        + digits(message_length, 5, required=True, zero_pad=True)
        + (" " * 25)
    )
    assert len(segment.encode(encoding)) == STM_WIDTH
    return segment


def serialize_question(
    question: Question,
    emitter: Emitter,
    emitted_at: datetime,
    *,
    encoding: str = "windows-1252",
    max_line_bytes: int = 8136,
) -> bytes:
    tail = (
        build_ste(emitter, emitted_at, encoding=encoding)
        + build_q00(emitter, question, encoding=encoding)
        + build_q01(question, encoding=encoding)
    )
    message_length = STM_WIDTH + len(tail.encode(encoding))
    message = build_stm(message_length, encoding=encoding) + tail
    payload = message.encode(encoding)
    if len(payload) != message_length:
        raise AssertionError("rendered message does not match declared STM length")
    if len(payload) > max_line_bytes:
        raise ValueError(
            f"message is {len(payload)} bytes; AGIRA maximum is {max_line_bytes}"
        )
    return payload


def default_filename(batch: QuestionBatch, emitted_at: datetime) -> str:
    application_code = APPLICATION_CODES[batch.environment]
    return (
        f"RA-{batch.account_code}-{application_code}."
        f"{batch.account_code}_{emitted_at:%Y%m%d}{batch.sequence:04d}.TXT"
    )


def serialize_batch(
    batch: QuestionBatch,
    *,
    encoding: str = "windows-1252",
    max_line_bytes: int = 8136,
) -> SerializedBatch:
    emitted_at = batch.emitted_at or datetime.now().astimezone().replace(tzinfo=None)
    lines = [
        serialize_question(
            question,
            batch.emitter,
            emitted_at,
            encoding=encoding,
            max_line_bytes=max_line_bytes,
        )
        for question in batch.questions
    ]
    payload = b"\r\n".join(lines) + b"\r\n"
    filename = safe_filename(
        batch.output_filename or default_filename(batch, emitted_at)
    )
    return SerializedBatch(
        batch_id=str(uuid.uuid4()),
        filename=filename,
        application_code=APPLICATION_CODES[batch.environment],
        payload=payload,
        sha256=hashlib.sha256(payload).hexdigest(),
        query_ids=[question.query_id for question in batch.questions],
    )

