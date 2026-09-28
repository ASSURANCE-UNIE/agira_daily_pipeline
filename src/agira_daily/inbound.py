from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal

from agira_api import agira_to_json
from agira_api.storage import atomic_write_bytes, atomic_write_json


InboundCategory = Literal["rej", "resp"]
QUESTION_MESSAGE_TYPES = {"AGQUES", "AGREPO", "FUNCTIONAL_REPLY"}
TERMINATION_MESSAGE_TYPES = {"AGRESC", "AGRESM", "AGRESS"}
_RECEPTION_DATE = re.compile(
    r"(?<!\d)(?P<date>20\d{6})(?:\d{6}(?:\d{3})?)?(?!\d)"
)
_REJECTION_NAME = re.compile(r"(?:^|[_.-])REJ(?:[_.-]|$)", re.IGNORECASE)
_RESPONSE_NAME = re.compile(r"(?:^|[_.-])REP(?:[_.-]|$)", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class InboundArchive:
    source_path: Path
    category: InboundCategory
    received_date: date
    history_dir: Path
    original_path: Path
    json_path: Path
    document_type: str
    status: Literal["archived", "already_archived"]
    source_deleted: bool


def discover_inbound_files(depot_root: Path) -> list[Path]:
    """Return every non-placeholder file from both inbound depot folders."""
    inbound_root = depot_root / "interrogations"
    sources: list[Path] = []
    for category in ("rej", "resp"):
        directory = inbound_root / category
        if not directory.exists():
            continue
        sources.extend(
            path
            for path in directory.iterdir()
            if path.is_file() and path.name != ".gitkeep" and not path.name.startswith(".")
        )
    return sorted(sources, key=lambda path: (path.name.casefold(), str(path.parent)))


def _received_date(filename: str) -> date:
    match = _RECEPTION_DATE.search(filename)
    if match is None:
        raise ValueError(
            f"cannot determine reception date from AGIRA filename {filename!r}"
        )
    try:
        return datetime.strptime(match.group("date"), "%Y%m%d").date()
    except ValueError as exc:
        raise ValueError(
            f"AGIRA filename {filename!r} contains an invalid reception date"
        ) from exc


def _message_payload(
    payload: bytes,
    raw: dict[str, Any],
    allowed_types: set[str],
) -> bytes:
    lines = payload.splitlines()
    selected_line_numbers = {
        int(message["line_number"])
        for message in raw["messages"]
        if message.get("message_type") in allowed_types
    }
    selected = [
        line
        for line_number, line in enumerate(lines, start=1)
        if line_number in selected_line_numbers
    ]
    return b"\r\n".join(selected) + (b"\r\n" if selected else b"")


def _translate(payload: bytes, filename: str, encoding: str) -> tuple[dict[str, Any], dict[str, Any]]:
    raw = agira_to_json(
        payload,
        source_filename=filename,
        kind="raw",
        encoding=encoding,
    )
    message_types = {
        str(message.get("message_type"))
        for message in raw["messages"]
        if message.get("message_type")
    }
    has_questions = bool(message_types & QUESTION_MESSAGE_TYPES)
    has_terminations = bool(message_types & TERMINATION_MESSAGE_TYPES)
    has_other_messages = bool(
        message_types - QUESTION_MESSAGE_TYPES - TERMINATION_MESSAGE_TYPES
    )

    if has_questions and not has_terminations and not has_other_messages:
        translated = agira_to_json(
            payload,
            source_filename=filename,
            kind="responses",
            encoding=encoding,
        )
    elif has_terminations and not has_questions and not has_other_messages:
        translated = agira_to_json(
            payload,
            source_filename=filename,
            kind="termination-responses",
            encoding=encoding,
        )
    elif has_questions and has_terminations and not has_other_messages:
        question_payload = _message_payload(payload, raw, QUESTION_MESSAGE_TYPES)
        termination_payload = _message_payload(
            payload, raw, TERMINATION_MESSAGE_TYPES
        )
        questions = agira_to_json(
            question_payload,
            source_filename=filename,
            kind="responses",
            encoding=encoding,
        )
        terminations = agira_to_json(
            termination_payload,
            source_filename=filename,
            kind="termination-responses",
            encoding=encoding,
        )
        translated = {
            "document_type": "agira_mixed_result_file",
            "source_filename": filename,
            "encoding": encoding,
            "summary": {
                "line_count": raw["line_count"],
                "parsed_message_count": raw["message_count"],
                "question_message_count": len(questions["protocol_messages"]),
                "termination_message_count": terminations["summary"]["record_count"],
                "warning_count": len(raw["warnings"]),
                "file_error_count": len(raw["file_errors"]),
                "is_parseable": not raw["file_errors"],
            },
            "question_results": questions,
            "termination_results": terminations,
            "warnings": raw["warnings"],
            "file_errors": raw["file_errors"],
        }
    else:
        translated = {
            "document_type": "agira_raw_result_file",
            **raw,
        }
    return translated, raw


def _category(source_path: Path, raw: dict[str, Any]) -> InboundCategory:
    filename = source_path.name
    if _REJECTION_NAME.search(filename) or "CSHRFR" in filename.upper():
        return "rej"
    if _RESPONSE_NAME.search(filename) or "CSHOFR" in filename.upper():
        return "resp"

    if any(message.get("errors") for message in raw["messages"]):
        return "rej"
    if raw["file_errors"]:
        return "rej"
    if source_path.parent.name.casefold() in {"rej", "resp"}:
        return source_path.parent.name.casefold()  # type: ignore[return-value]
    raise ValueError(f"cannot classify AGIRA inbound file {filename!r}")


def _check_existing_bytes(path: Path, expected: bytes) -> bool:
    if not path.exists():
        return False
    if path.read_bytes() != expected:
        raise FileExistsError(f"history conflict: {path} contains different bytes")
    return True


def _check_existing_json(path: Path, expected: dict[str, Any]) -> bool:
    if not path.exists():
        return False
    try:
        existing = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise FileExistsError(f"history conflict: {path} is not valid UTF-8 JSON") from exc
    if existing != expected:
        raise FileExistsError(f"history conflict: {path} contains different JSON")
    return True


def archive_inbound_file(
    source_path: Path,
    *,
    history_root: Path,
    encoding: str = "windows-1252",
    delete_source: bool = True,
) -> InboundArchive:
    """Translate and archive one AGIRA reception file, then clear the depot."""
    source_path = source_path.resolve()
    if not source_path.is_file():
        raise FileNotFoundError(source_path)
    if delete_source and not (
        source_path.parent.name.casefold() in {"rej", "resp"}
        and source_path.parent.parent.name.casefold() == "interrogations"
    ):
        raise ValueError(
            f"refusing to delete inbound source outside an interrogations depot: "
            f"{source_path}"
        )

    payload = source_path.read_bytes()
    translated, raw = _translate(payload, source_path.name, encoding)
    category = _category(source_path, raw)
    received_date = _received_date(source_path.name)
    history_dir = (
        history_root.resolve()
        / "interrogations"
        / category
        / received_date.isoformat()
    )
    original_path = history_dir / source_path.name
    json_path = history_dir / source_path.with_suffix(".json").name

    original_exists = _check_existing_bytes(original_path, payload)
    json_exists = _check_existing_json(json_path, translated)
    if not original_exists:
        atomic_write_bytes(original_path, payload)
    if not json_exists:
        atomic_write_json(json_path, translated)

    if delete_source:
        _check_existing_bytes(original_path, payload)
        _check_existing_json(json_path, translated)
        source_path.unlink()

    return InboundArchive(
        source_path=source_path,
        category=category,
        received_date=received_date,
        history_dir=history_dir,
        original_path=original_path,
        json_path=json_path,
        document_type=str(translated["document_type"]),
        status=(
            "already_archived"
            if original_exists and json_exists
            else "archived"
        ),
        source_deleted=delete_source,
    )
