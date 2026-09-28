from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping

from .models import QuestionBatch, TerminationBatch
from .parser import parse_reply_bytes
from .serializer import serialize_batch
from .termination_serializer import serialize_termination_batch
from .translators import (
    translate_question_bytes,
    translate_response_bytes,
    translate_termination_request_bytes,
    translate_termination_response_bytes,
)


AgiraDocumentKind = Literal[
    "raw",
    "questions",
    "responses",
    "termination-requests",
    "termination-responses",
]


@dataclass(frozen=True, slots=True)
class RenderedDocument:
    """An AGIRA file rendered from a validated business JSON document."""

    filename: str
    payload: bytes
    sha256: str
    document_type: Literal["questions", "terminations"]
    item_count: int


def json_to_agira(
    document: Mapping[str, Any],
    *,
    encoding: str = "windows-1252",
    max_line_bytes: int = 8136,
) -> RenderedDocument:
    """Validate business JSON and render the corresponding AGIRA TXT file.

    The top-level ``questions`` or ``records`` key selects the schema. Keeping
    this dispatch explicit prevents malformed input from being silently
    interpreted as another AGIRA message family.
    """

    has_questions = "questions" in document
    has_terminations = "records" in document
    if has_questions == has_terminations:
        raise ValueError(
            "JSON must contain exactly one discriminator: 'questions' or 'records'"
        )

    if has_questions:
        batch = QuestionBatch.model_validate(document)
        rendered = serialize_batch(
            batch,
            encoding=encoding,
            max_line_bytes=max_line_bytes,
        )
        return RenderedDocument(
            filename=rendered.filename,
            payload=rendered.payload,
            sha256=rendered.sha256,
            document_type="questions",
            item_count=len(batch.questions),
        )

    batch = TerminationBatch.model_validate(document)
    rendered = serialize_termination_batch(
        batch,
        encoding=encoding,
        max_line_bytes=max_line_bytes,
    )
    return RenderedDocument(
        filename=rendered.filename,
        payload=rendered.payload,
        sha256=rendered.sha256,
        document_type="terminations",
        item_count=len(batch.records),
    )


def agira_to_json(
    payload: bytes,
    *,
    source_filename: str,
    kind: AgiraDocumentKind = "raw",
    encoding: str = "windows-1252",
    max_line_bytes: int = 8136,
) -> dict[str, Any]:
    """Translate an AGIRA file into JSON without filesystem side effects.

    ``raw`` is deliberately the default because an accepted termination reply
    can be byte-for-byte identical to the submitted request. Callers that know
    the channel can select a semantic view explicitly.
    """

    arguments = {
        "source_filename": source_filename,
        "encoding": encoding,
        "max_line_bytes": max_line_bytes,
    }
    if kind == "raw":
        return parse_reply_bytes(payload, **arguments)
    translators = {
        "questions": translate_question_bytes,
        "responses": translate_response_bytes,
        "termination-requests": translate_termination_request_bytes,
        "termination-responses": translate_termination_response_bytes,
    }
    return translators[kind](payload, **arguments)
