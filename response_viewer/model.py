"""Pure data helpers for the standalone AGIRA response viewer."""

from __future__ import annotations

import json
from collections import OrderedDict
from pathlib import Path
from typing import Any, Iterable


CRITERIA_LABELS = OrderedDict(
    [
        ("previous_insurer_company_code", "Previous insurer"),
        ("contract_number", "Contract number"),
        ("last_name_or_company_name", "Name / company"),
        ("birth_or_maiden_name", "Birth / maiden name"),
        ("first_name", "First name"),
        ("birth_date", "Birth date"),
        ("residence_postal_code", "Postal code"),
        ("driving_licence_date", "Licence date"),
        ("registration_number", "Registration"),
        ("siren", "SIREN"),
    ]
)


def parse_response(payload: bytes | str) -> dict[str, Any]:
    """Parse and minimally validate an AGIRA response JSON document."""
    if isinstance(payload, bytes):
        try:
            payload = payload.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError("The file is not valid UTF-8 JSON.") from exc

    try:
        document = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON near line {exc.lineno}, column {exc.colno}.") from exc

    if not isinstance(document, dict):
        raise ValueError("The JSON root must be an object.")
    conversations = document.get("conversations")
    if not isinstance(conversations, list):
        raise ValueError("This is not an AGIRA response JSON: 'conversations' is missing.")
    return document


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def contract_id(conversation: dict[str, Any]) -> str:
    parts = conversation.get("query_id_parts") or {}
    number = parts.get("numero_police")
    if number:
        return str(number)

    query_id = str(conversation.get("query_id") or "")
    if "-" in query_id:
        return query_id.split("-", 1)[0]
    return query_id or "Unknown contract"


def segment_code(conversation: dict[str, Any]) -> str:
    parts = conversation.get("query_id_parts") or {}
    code = parts.get("correspondence_code")
    if code:
        return f"C{str(code).removeprefix('C')}"
    query_id = str(conversation.get("query_id") or "")
    return query_id.rsplit("-", 1)[-1] if "-" in query_id else "—"


def segment_sort_key(conversation: dict[str, Any]) -> tuple[int, str]:
    code = segment_code(conversation).removeprefix("C")
    try:
        return int(code), str(conversation.get("query_id") or "")
    except ValueError:
        return 999, str(conversation.get("query_id") or "")


def group_contracts(document: dict[str, Any]) -> OrderedDict[str, list[dict[str, Any]]]:
    grouped: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
    for conversation in document.get("conversations", []):
        if not isinstance(conversation, dict):
            continue
        grouped.setdefault(contract_id(conversation), []).append(conversation)
    for conversations in grouped.values():
        conversations.sort(key=segment_sort_key)
    return grouped


def display_value(value: Any) -> str:
    """Turn nested AGIRA values, especially parsed dates, into compact text."""
    if value is None or value == "":
        return "—"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, dict):
        if value.get("iso"):
            return str(value["iso"])
        year = value.get("year")
        month = value.get("month")
        day = value.get("day")
        if year:
            chunks = [str(year).zfill(4)]
            if month:
                chunks.append(str(month).zfill(2))
            if day:
                chunks.append(str(day).zfill(2))
            return "-".join(chunks)
        if value.get("raw"):
            return str(value["raw"])
        return ", ".join(f"{key}: {display_value(item)}" for key, item in value.items())
    if isinstance(value, list):
        return ", ".join(display_value(item) for item in value) or "—"
    return str(value)


def criteria_items(conversation: dict[str, Any]) -> list[tuple[str, str]]:
    criteria = (conversation.get("query") or {}).get("criteria") or {}
    return [
        (label, display_value(criteria.get(key)))
        for key, label in CRITERIA_LABELS.items()
        if criteria.get(key) not in (None, "", [])
    ]


def criteria_summary(conversation: dict[str, Any]) -> str:
    items = criteria_items(conversation)
    return " · ".join(f"{label}: {value}" for label, value in items) or "No criteria"


def returned_records(conversations: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        record
        for conversation in conversations
        for record in as_list(conversation.get("records"))
        if isinstance(record, dict)
    ]


def returned_contract_number(record: dict[str, Any]) -> str:
    return str((record.get("contract") or {}).get("contract_number") or "—")


def contract_overview(
    grouped: OrderedDict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    rows = []
    for number, conversations in grouped.items():
        records = returned_records(conversations)
        returned_numbers = list(dict.fromkeys(returned_contract_number(record) for record in records))
        matched = sum(conversation.get("status") == "matched" for conversation in conversations)
        rows.append(
            {
                "Submitted contract": number,
                "Segments": len(conversations),
                "Matched": matched,
                "No match": len(conversations) - matched,
                "Returned records": len(records),
                "Returned contract(s)": ", ".join(returned_numbers) if records else "—",
            }
        )
    return rows


def summary_counts(grouped: OrderedDict[str, list[dict[str, Any]]]) -> dict[str, int]:
    conversations = [item for items in grouped.values() for item in items]
    matched = sum(item.get("status") == "matched" for item in conversations)
    return {
        "contracts": len(grouped),
        "segments": len(conversations),
        "matched": matched,
        "no_match": len(conversations) - matched,
        "records": len(returned_records(conversations)),
    }


def history_files(root: Path) -> list[Path]:
    """Archived RESP JSON files (history/.../resp/YYYY-MM-DD/*.json), newest first."""
    return sorted(root.glob("*/*.json"), key=lambda path: (path.parent.name, path.name), reverse=True)


def matching_contracts(
    grouped: OrderedDict[str, list[dict[str, Any]]],
    police: str,
) -> list[str]:
    """Contracts whose numero_police contains the search text (case-insensitive)."""
    needle = police.strip().casefold()
    return [number for number in grouped if needle in number.casefold()]
