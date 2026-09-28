from __future__ import annotations

import re
from collections import Counter
from typing import Any

from .parser import parse_reply_bytes


# outbound query ids built by the separate daily pipeline:
# numero_police-YYYYMMDD-row-Cfamily (the police part may contain dashes)
_QUERY_ID_PARTS = re.compile(
    r"^(?P<numero_police>.+)-(?P<emitted_date>\d{8})"
    r"-(?P<row>\d{6})-C(?P<correspondence_code>\d{2})$"
)


def _query_id_parts(query_id: str | None) -> dict[str, str] | None:
    """Best-effort split of a query id into numero_police/date/row/family.

    Returns None for legacy or unrelated id shapes; the batch mapping file
    remains the authoritative correlation.
    """
    match = _QUERY_ID_PARTS.match(query_id or "")
    return match.groupdict() if match else None


TERMINATION_REASON_LABELS = {
    "1": "insurer termination - contract nullity",
    "2": "insurer termination - non-payment of premium",
    "3": "insurer termination during the contract after a claim",
    "4": "insurer termination at contract expiry",
    "5": "insured termination or disappearance of the risk",
}

TERMINATION_MESSAGE_TYPES = {"AGRESC", "AGRESM", "AGRESS"}


def _protocol(message: dict[str, Any]) -> dict[str, Any]:
    stm = message.get("stm") or {}
    return {
        "layout": message.get("layout"),
        "line_number": message.get("line_number"),
        "message_code": message.get("message_type"),
        "message_version": stm.get("version"),
        "origin": stm.get("origin"),
        "declared_length": stm.get("declared_length"),
        "declared_length_scope": message.get("declared_length_scope"),
        "functional_message_length": message.get("functional_message_length"),
        "physical_length": message.get("physical_length"),
    }


def _business_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _business_value(item)
            for key, item in value.items()
            if key not in {"segment", "filler", "sender_padding", "recipient_padding"}
        }
    if isinstance(value, list):
        return [_business_value(item) for item in value]
    return value


def translate_question_bytes(
    payload: bytes,
    *,
    source_filename: str,
    encoding: str = "windows-1252",
    max_line_bytes: int = 8136,
) -> dict[str, Any]:
    parsed = parse_reply_bytes(
        payload,
        source_filename=source_filename,
        encoding=encoding,
        max_line_bytes=max_line_bytes,
    )
    questions: list[dict[str, Any]] = []
    errors = list(parsed["file_errors"])
    for message in parsed["messages"]:
        if message.get("message_type") != "AGQUES":
            errors.append(
                {
                    "line": message.get("line_number"),
                    "error": (
                        f"expected AGQUES question message, found "
                        f"{message.get('message_type')!r}"
                    ),
                }
            )
            continue
        identification = message.get("query_identification") or {}
        sender = message.get("sender") or {}
        questions.append(
            {
                "line_number": message.get("line_number"),
                "query_id": identification.get("company_query_identifier"),
                "server_query_id": identification.get("server_internal_identifier"),
                "emitter": _business_value(sender.get("sender")),
                "emitted_at_raw": sender.get("emission_timestamp_raw"),
                "criteria": _business_value(message.get("criteria")),
                "errors": _business_value(message.get("errors", [])),
                "warnings": message.get("warnings", []),
                "protocol": _protocol(message),
            }
        )
    query_ids = [item["query_id"] for item in questions if item["query_id"]]
    query_id_counts = Counter(query_ids)
    duplicate_query_ids = sorted(
        query_id for query_id, count in query_id_counts.items() if count > 1
    )
    if duplicate_query_ids:
        errors.append(
            {
                "line": None,
                "error": "duplicate query identifiers",
                "query_ids": duplicate_query_ids,
            }
        )
    return {
        "document_type": "agira_question_file",
        "source_filename": source_filename,
        "encoding": encoding,
        "summary": {
            "line_count": parsed["line_count"],
            "question_count": len(questions),
            "unique_query_id_count": len(set(query_ids)),
            "warning_count": len(parsed["warnings"]),
            "error_count": len(errors)
            + sum(len(item["errors"]) for item in questions),
            "is_valid": not errors
            and all(not item["errors"] for item in questions)
            and len(questions) == parsed["line_count"],
        },
        "questions": questions,
        "warnings": parsed["warnings"],
        "errors": errors,
    }


def _clear_query(query: dict[str, Any] | None) -> dict[str, Any] | None:
    if query is None:
        return None
    return {
        "criteria": _business_value(query.get("criteria")),
        "emitter": _business_value((query.get("sender") or {}).get("sender")),
        "emitted_at_raw": (query.get("sender") or {}).get("emission_timestamp_raw"),
        "protocol": _protocol(query) if query.get("message_type") else {
            "layout": query.get("layout")
        },
    }


def _clear_conversation(conversation: dict[str, Any]) -> dict[str, Any]:
    raw_results = conversation.get("results", [])
    records = [
        _business_value(result.get("record"))
        for result in raw_results
        if result.get("record")
    ]
    matches = [
        _business_value(match)
        for result in raw_results
        for match in result.get("matches", [])
    ]
    errors = conversation.get("errors", [])
    query = conversation.get("query")
    if errors:
        status = "rejected"
    elif records:
        status = "matched"
    elif matches:
        status = "match_indication_only"
    elif query is not None:
        status = "no_match"
    else:
        status = "orphan_response"
    return {
        "query_id": conversation.get("query_id"),
        "query_id_parts": _query_id_parts(conversation.get("query_id")),
        "status": status,
        "query": _clear_query(query),
        "match_reasons": matches,
        "records": records,
        "errors": _business_value(errors),
        "result_protocol": [
            _protocol(result) if result.get("message_type") else {
                "layout": result.get("layout")
            }
            for result in raw_results
        ],
    }


def translate_response_bytes(
    payload: bytes,
    *,
    source_filename: str,
    encoding: str = "windows-1252",
    max_line_bytes: int = 8136,
) -> dict[str, Any]:
    parsed = parse_reply_bytes(
        payload,
        source_filename=source_filename,
        encoding=encoding,
        max_line_bytes=max_line_bytes,
    )
    conversations = [
        _clear_conversation(conversation)
        for conversation in parsed["conversations"]
    ]
    statuses: dict[str, int] = {}
    for conversation in conversations:
        status = conversation["status"]
        statuses[status] = statuses.get(status, 0) + 1
    returned_record_count = sum(
        len(conversation["records"]) for conversation in conversations
    )
    conversation_lines = {
        message.get("line_number")
        for message in parsed["messages"]
        if message.get("message_type") in {"AGQUES", "AGREPO", "FUNCTIONAL_REPLY"}
    }
    other_messages = [
        {
            "line_number": message.get("line_number"),
            "message_type": message.get("message_type"),
            "errors": _business_value(message.get("errors", [])),
            "warnings": message.get("warnings", []),
            "protocol": _protocol(message),
            "raw_body_after_stm": message.get("raw_functional_body"),
        }
        for message in parsed["messages"]
        if message.get("line_number") not in conversation_lines
    ]
    rejection_count = sum(
        len(message.get("errors", [])) for message in parsed["messages"]
    )
    return {
        "document_type": "agira_response_file",
        "source_filename": source_filename,
        "encoding": encoding,
        "summary": {
            "line_count": parsed["line_count"],
            "parsed_message_count": parsed["message_count"],
            "conversation_count": len(conversations),
            "returned_record_count": returned_record_count,
            "rejection_count": rejection_count,
            "statuses": statuses,
            "warning_count": len(parsed["warnings"]),
            "file_error_count": len(parsed["file_errors"]),
            "is_parseable": not parsed["file_errors"],
        },
        "conversations": conversations,
        "other_messages": other_messages,
        "warnings": parsed["warnings"],
        "file_errors": parsed["file_errors"],
        "protocol_messages": parsed["messages"],
    }


def _clear_termination_record(message: dict[str, Any]) -> dict[str, Any]:
    record = _business_value(message.get("record") or {})
    termination = record.get("termination")
    if termination:
        termination["reason_label"] = TERMINATION_REASON_LABELS.get(
            termination.get("reason_code"), "unknown reason code"
        )
    sender = message.get("sender") or {}
    return {
        "line_number": message.get("line_number"),
        "operation": message.get("operation"),
        "message_code": message.get("message_type"),
        "company_record_id": (
            (record.get("identification") or {}).get("company_record_identifier")
        ),
        "emitter": _business_value(sender.get("sender")),
        "emitted_at_raw": sender.get("emission_timestamp_raw"),
        "record": record,
        "errors": _business_value(message.get("errors", [])),
        "warnings": message.get("warnings", []),
        "protocol": _protocol(message),
    }


def _translate_termination_bytes(
    payload: bytes,
    *,
    source_filename: str,
    response_file: bool,
    encoding: str,
    max_line_bytes: int,
) -> dict[str, Any]:
    parsed = parse_reply_bytes(
        payload,
        source_filename=source_filename,
        encoding=encoding,
        max_line_bytes=max_line_bytes,
    )
    records: list[dict[str, Any]] = []
    errors = list(parsed["file_errors"])
    for message in parsed["messages"]:
        if message.get("message_type") not in TERMINATION_MESSAGE_TYPES:
            errors.append(
                {
                    "line": message.get("line_number"),
                    "error": (
                        "expected AGRESC, AGRESM, or AGRESS termination message, "
                        f"found {message.get('message_type')!r}"
                    ),
                }
            )
            continue
        record = _clear_termination_record(message)
        if response_file:
            record["status"] = "rejected" if record["errors"] else "accepted"
        else:
            record["status"] = "invalid" if record["errors"] else "ready_to_send"
        records.append(record)

    operation_counts = dict(Counter(record["operation"] for record in records))
    status_counts = dict(Counter(record["status"] for record in records))
    message_error_count = sum(len(record["errors"]) for record in records)
    document_type = (
        "agira_termination_response_file"
        if response_file
        else "agira_termination_request_file"
    )
    return {
        "document_type": document_type,
        "source_filename": source_filename,
        "encoding": encoding,
        "summary": {
            "line_count": parsed["line_count"],
            "record_count": len(records),
            "operation_counts": operation_counts,
            "status_counts": status_counts,
            "accepted_count": status_counts.get("accepted", 0),
            "rejected_count": status_counts.get("rejected", 0),
            "warning_count": len(parsed["warnings"]),
            "file_error_count": len(errors),
            "error_count": len(errors) + message_error_count,
            "is_valid": not errors and not message_error_count,
        },
        "records": records,
        "warnings": parsed["warnings"],
        "errors": errors,
    }


def translate_termination_request_bytes(
    payload: bytes,
    *,
    source_filename: str,
    encoding: str = "windows-1252",
    max_line_bytes: int = 8136,
) -> dict[str, Any]:
    return _translate_termination_bytes(
        payload,
        source_filename=source_filename,
        response_file=False,
        encoding=encoding,
        max_line_bytes=max_line_bytes,
    )


def translate_termination_response_bytes(
    payload: bytes,
    *,
    source_filename: str,
    encoding: str = "windows-1252",
    max_line_bytes: int = 8136,
) -> dict[str, Any]:
    return _translate_termination_bytes(
        payload,
        source_filename=source_filename,
        response_file=True,
        encoding=encoding,
        max_line_bytes=max_line_bytes,
    )
