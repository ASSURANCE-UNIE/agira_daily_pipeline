from __future__ import annotations

from datetime import date
from typing import Any


STM_WIDTH = 42
STE_WIDTH = 52
STD_WIDTH = 36
Q00_WIDTHS = (69, 72)
Q01_WIDTH = 123
MATCH_WIDTH = 37
ERROR_WIDTH = 41


class ParseError(ValueError):
    """Raised when a physical line cannot be interpreted safely."""


def _value(raw: str) -> str | None:
    value = raw.strip()
    return value or None


def _date_value(raw: str) -> dict[str, Any] | None:
    text = raw.strip()
    if not text:
        return None
    result: dict[str, Any] = {"raw": text}
    if len(text) != 8 or not text.isdigit():
        result["valid"] = False
        return result
    day, month, year = text[:2], text[2:4], text[4:]
    if day == "00" or month == "00":
        result.update(
            {
                "valid": True,
                "partial": True,
                "year": int(year),
                "month": None if month == "00" else int(month),
                "day": None if day == "00" else int(day),
            }
        )
        return result
    try:
        parsed = date(int(year), int(month), int(day))
    except ValueError:
        result["valid"] = False
        return result
    result.update({"valid": True, "partial": False, "iso": parsed.isoformat()})
    return result


def _integer(raw: str) -> int | None:
    text = raw.strip()
    return int(text) if text.isdigit() else None


def _require_code(raw: str, code: str) -> None:
    if not raw.startswith(code):
        raise ParseError(f"expected segment {code!r}, found {raw[:3]!r}")


def parse_stm(raw: str) -> dict[str, Any]:
    if len(raw) != STM_WIDTH:
        raise ParseError(f"STM must be {STM_WIDTH} characters")
    _require_code(raw, "STM")
    declared = _integer(raw[12:17])
    if declared is None:
        raise ParseError("STM message length is not numeric")
    return {
        "segment": "STM",
        "message_code": _value(raw[3:9]),
        "version": _value(raw[9:11]),
        "origin": _value(raw[11:12]),
        "declared_length": declared,
        "filler": raw[17:42],
    }


def _parse_company_identity(raw: str) -> dict[str, Any]:
    if len(raw) < 14:
        raise ParseError("company identity must contain at least 14 characters")
    return {
        "country_code": _value(raw[0:3]),
        "company_code": _value(raw[3:9]),
        "internal_company_code": _value(raw[9:14]),
    }


def parse_ste(raw: str) -> dict[str, Any]:
    if len(raw) != STE_WIDTH:
        raise ParseError(f"STE must be {STE_WIDTH} characters")
    _require_code(raw, "STE")
    return {
        "segment": "STE",
        "sender_type": _value(raw[3:4]),
        "sender": _parse_company_identity(raw[4:18]),
        "sender_padding": raw[18:21],
        "emission_timestamp_raw": _value(raw[21:35]),
        "emission_mode": _value(raw[35:36]),
        "sender_message_identifier": _value(raw[36:52]),
    }


def parse_std(raw: str) -> dict[str, Any]:
    if len(raw) != STD_WIDTH:
        raise ParseError(f"STD must be {STD_WIDTH} characters")
    _require_code(raw, "STD")
    return {
        "segment": "STD",
        "recipient_type": _value(raw[3:4]),
        "recipient": _parse_company_identity(raw[4:18]),
        "recipient_padding": raw[18:21],
        "emission_timestamp_raw": _value(raw[21:35]),
        "emission_mode": _value(raw[35:36]),
    }


def parse_q00(raw: str) -> dict[str, Any]:
    if len(raw) not in Q00_WIDTHS:
        raise ParseError(f"Q00 must be one of {Q00_WIDTHS} characters")
    _require_code(raw, "Q00")
    company_width = 17 if len(raw) == 72 else 14
    company_raw = raw[3 : 3 + company_width]
    cursor = 3 + company_width
    result = {
        "segment": "Q00",
        "observed_width": len(raw),
        "company": _parse_company_identity(company_raw[:14]),
        "company_query_identifier": _value(raw[cursor : cursor + 40]),
        "server_internal_identifier": _value(raw[cursor + 40 : cursor + 52]),
    }
    if company_width == 17:
        result["company_padding"] = company_raw[14:17]
    return result


def parse_q01(raw: str) -> dict[str, Any]:
    if len(raw) != Q01_WIDTH:
        raise ParseError(f"Q01 must be {Q01_WIDTH} characters")
    _require_code(raw, "Q01")
    return {
        "segment": "Q01",
        "previous_insurer_company_code": _value(raw[3:9]),
        "contract_number": _value(raw[9:29]),
        "last_name_or_company_name": _value(raw[29:49]),
        "birth_or_maiden_name": _value(raw[49:69]),
        "first_name": _value(raw[69:81]),
        "birth_date": _date_value(raw[81:89]),
        "residence_postal_code": _value(raw[89:94]),
        "driving_licence_date": _date_value(raw[94:102]),
        "registration_number": _value(raw[102:114]),
        "siren": _value(raw[114:123]),
    }


def parse_match(raw: str) -> dict[str, Any]:
    if len(raw) != MATCH_WIDTH:
        raise ParseError(f"006 must be {MATCH_WIDTH} characters")
    _require_code(raw, "006")
    return {
        "segment": "006",
        "match_code": _value(raw[3:5]),
        "match_label": _value(raw[5:37]),
    }


def parse_error(raw: str) -> dict[str, Any]:
    if len(raw) != ERROR_WIDTH:
        raise ParseError(f"STR must be {ERROR_WIDTH} characters")
    _require_code(raw, "STR")
    detail = raw[11:41]
    result: dict[str, Any] = {
        "segment": "STR",
        "error_code": _value(raw[3:8]),
        "segment_in_error": _value(raw[8:11]),
        "detail": _value(detail),
    }
    if (
        result["error_code"]
        in {"00002", "00003", "00004", "00005", "00006", "00007"}
        and detail[0:3].isdigit()
        and detail[3:7].isdigit()
    ):
        result["detail_parts"] = {
            "functional_segment_rank": _integer(detail[0:3]),
            "data_code": _value(detail[3:7]),
            "label": _value(detail[7:30]),
        }
    return result


def parse_record_id(raw: str) -> dict[str, Any]:
    if len(raw) != 57:
        raise ParseError("000 must be 57 characters")
    _require_code(raw, "000")
    return {
        "segment": "000",
        "company": _parse_company_identity(raw[3:17]),
        "company_record_identifier": _value(raw[17:57]),
    }


def parse_contract(raw: str) -> dict[str, Any]:
    if len(raw) != 49:
        raise ParseError("001 must be 49 characters")
    _require_code(raw, "001")
    crm = _value(raw[45:49])
    return {
        "segment": "001",
        "company": _parse_company_identity(raw[3:17]),
        "contract_number": _value(raw[17:37]),
        "effective_date": _date_value(raw[37:45]),
        "bonus_malus_coefficient": crm.replace(",", ".") if crm else None,
        "bonus_malus_coefficient_raw": crm,
    }


def parse_person(raw: str) -> dict[str, Any]:
    if len(raw) != 238:
        raise ParseError("002 must be 238 characters in strict v3.1 mode")
    _require_code(raw, "002")
    return {
        "segment": "002",
        "role": {"S": "subscriber", "C": "driver"}.get(raw[3:4], _value(raw[3:4])),
        "name_or_company_name": _value(raw[4:24]),
        "first_name": _value(raw[24:36]),
        "person_kind": "legal_entity" if raw[36:37] == "1" else "natural_person",
        "birth_date": _date_value(raw[37:45]),
        "address_lines": [value for value in (_value(raw[45:77]), _value(raw[77:109]), _value(raw[109:141]), _value(raw[141:173])) if value],
        "postal_code": _value(raw[173:178]),
        "city": _value(raw[178:204]),
        "siren": _value(raw[204:213]),
        "licence_issue_postal_code": _value(raw[213:218]),
        "driving_licence_number": _value(raw[218:230]),
        "driving_licence_date": _date_value(raw[230:238]),
    }


def parse_termination(raw: str) -> dict[str, Any]:
    if len(raw) != 12:
        raise ParseError("003 must be 12 characters")
    _require_code(raw, "003")
    return {
        "segment": "003",
        "reason_code": _value(raw[3:4]),
        "termination_date": _date_value(raw[4:12]),
    }


def parse_claim(raw: str) -> dict[str, Any]:
    if len(raw) != 69:
        raise ParseError("004 must be 69 characters")
    _require_code(raw, "004")
    return {
        "segment": "004",
        "claim_number": _value(raw[3:23]),
        "nature_code": _value(raw[23:24]),
        "claim_date": _date_value(raw[24:32]),
        "guarantee_code": _value(raw[32:34]),
        "responsibility_percent": _integer(raw[34:37]),
        "driver_last_name": _value(raw[37:57]),
        "driver_first_name": _value(raw[57:69]),
    }


def parse_vehicle(raw: str) -> dict[str, Any]:
    if len(raw) != 33:
        raise ParseError("005 must be 33 characters")
    _require_code(raw, "005")
    return {
        "segment": "005",
        "category_code": _value(raw[3:4]),
        "registration_number": _value(raw[4:16]),
        "manufacturer_code": _value(raw[16:19]),
        "type_mine": _value(raw[19:25]),
        "serial_number": _value(raw[25:33]),
    }


def parse_cnil(raw: str) -> dict[str, Any]:
    if len(raw) != 163:
        raise ParseError("007 must be 163 characters")
    _require_code(raw, "007")
    return {"segment": "007", "text": _value(raw[3:163])}


def _q00_width_before(text: str, start: int, next_code: str) -> int:
    matches = [width for width in Q00_WIDTHS if text.startswith(next_code, start + width)]
    if len(matches) != 1:
        raise ParseError(
            f"could not determine Q00 width before {next_code}; expected 69 or 72"
        )
    return matches[0]


def _parse_full_query(content: str, stm: dict[str, Any]) -> dict[str, Any]:
    cursor = STM_WIDTH
    sender = parse_ste(content[cursor : cursor + STE_WIDTH])
    cursor += STE_WIDTH
    q00_width = _q00_width_before(content, cursor, "Q01")
    query_identification = parse_q00(content[cursor : cursor + q00_width])
    cursor += q00_width
    criteria = parse_q01(content[cursor : cursor + Q01_WIDTH])
    cursor += Q01_WIDTH
    if cursor != len(content):
        raise ParseError(f"unexpected {len(content) - cursor} characters after AGQUES")
    return {
        "layout": "complete_v3_1",
        "message_type": "AGQUES",
        "stm": stm,
        "sender": sender,
        "query_identification": query_identification,
        "criteria": criteria,
        "warnings": [],
    }


def _parse_full_response(content: str, stm: dict[str, Any]) -> dict[str, Any]:
    cursor = STM_WIDTH
    recipient = parse_std(content[cursor : cursor + STD_WIDTH])
    cursor += STD_WIDTH
    q00_width = _q00_width_before(content, cursor, "006")
    query_identification = parse_q00(content[cursor : cursor + q00_width])
    cursor += q00_width

    matches: list[dict[str, Any]] = []
    while content.startswith("006", cursor) and len(matches) < 8:
        matches.append(parse_match(content[cursor : cursor + MATCH_WIDTH]))
        cursor += MATCH_WIDTH
    record_id = parse_record_id(content[cursor : cursor + 57])
    cursor += 57
    contract = parse_contract(content[cursor : cursor + 49])
    cursor += 49

    persons: list[dict[str, Any]] = []
    while content.startswith("002", cursor) and len(persons) < 5:
        persons.append(parse_person(content[cursor : cursor + 238]))
        cursor += 238
    termination = parse_termination(content[cursor : cursor + 12])
    cursor += 12

    claims: list[dict[str, Any]] = []
    while content.startswith("004", cursor) and len(claims) < 10:
        claims.append(parse_claim(content[cursor : cursor + 69]))
        cursor += 69
    vehicle = parse_vehicle(content[cursor : cursor + 33])
    cursor += 33

    cnil = None
    if content.startswith("007", cursor):
        cnil = parse_cnil(content[cursor : cursor + 163])
        cursor += 163
    if cursor != len(content):
        raise ParseError(f"unexpected {len(content) - cursor} characters after AGREPO")
    return {
        "layout": "complete_v3_1",
        "message_type": "AGREPO",
        "stm": stm,
        "recipient": recipient,
        "query_identification": query_identification,
        "matches": matches,
        "record": {
            "identification": record_id,
            "contract": contract,
            "persons": persons,
            "termination": termination,
            "claims": claims,
            "vehicle": vehicle,
            "cnil": cnil,
        },
        "warnings": [],
    }


def _parse_full_termination_submission(
    content: str,
    stm: dict[str, Any],
) -> dict[str, Any]:
    operation = {
        "AGRESC": "create",
        "AGRESM": "modify",
        "AGRESS": "delete",
    }[stm["message_code"]]
    cursor = STM_WIDTH
    sender = parse_ste(content[cursor : cursor + STE_WIDTH])
    cursor += STE_WIDTH
    record_id = parse_record_id(content[cursor : cursor + 57])
    cursor += 57

    record: dict[str, Any] = {"identification": record_id}
    if operation != "delete":
        contract = parse_contract(content[cursor : cursor + 49])
        cursor += 49
        persons: list[dict[str, Any]] = []
        while content.startswith("002", cursor) and len(persons) < 5:
            persons.append(parse_person(content[cursor : cursor + 238]))
            cursor += 238
        if not persons:
            raise ParseError("creation/modification requires at least one 002 segment")
        termination = parse_termination(content[cursor : cursor + 12])
        cursor += 12
        claims: list[dict[str, Any]] = []
        while content.startswith("004", cursor) and len(claims) < 10:
            claims.append(parse_claim(content[cursor : cursor + 69]))
            cursor += 69
        vehicle = parse_vehicle(content[cursor : cursor + 33])
        cursor += 33
        cnil = None
        if content.startswith("007", cursor):
            cnil = parse_cnil(content[cursor : cursor + 163])
            cursor += 163
        if termination["reason_code"] == "3" and not claims:
            raise ParseError("termination reason 3 requires at least one 004 segment")
        record.update(
            {
                "contract": contract,
                "persons": persons,
                "termination": termination,
                "claims": claims,
                "vehicle": vehicle,
                "cnil": cnil,
            }
        )
    if cursor != len(content):
        raise ParseError(
            f"unexpected {len(content) - cursor} characters after {stm['message_code']}"
        )
    return {
        "layout": "complete_v3_1",
        "message_type": stm["message_code"],
        "operation": operation,
        "stm": stm,
        "sender": sender,
        "record": record,
        "warnings": [],
    }


def _parse_str_tail(tail: str) -> tuple[list[dict[str, Any]], list[str]]:
    errors: list[dict[str, Any]] = []
    warnings: list[str] = []
    cursor = 0
    while cursor + ERROR_WIDTH <= len(tail) and tail.startswith("STR", cursor):
        errors.append(parse_error(tail[cursor : cursor + ERROR_WIDTH]))
        cursor += ERROR_WIDTH
    if cursor != len(tail):
        warnings.append(
            f"{len(tail) - cursor} trailing characters could not be parsed as STR"
        )
    return errors, warnings


def _parse_complete_content(content: str, stm: dict[str, Any]) -> dict[str, Any]:
    message_code = stm["message_code"]
    if message_code == "AGQUES":
        return _parse_full_query(content, stm)
    if message_code == "AGREPO":
        return _parse_full_response(content, stm)
    if message_code in {"AGRESC", "AGRESM", "AGRESS"}:
        return _parse_full_termination_submission(content, stm)
    return {
        "layout": "complete_v3_1",
        "message_type": message_code,
        "stm": stm,
        "raw_functional_body": content[STM_WIDTH:],
        "warnings": [
            f"message type {message_code!r} is preserved but not decoded by this API"
        ],
    }


def _trailing_str_start(line: str) -> int | None:
    """Return the start of up to five fixed-width STR segments at line end."""
    cursor = len(line)
    count = 0
    while (
        count < 5
        and cursor - ERROR_WIDTH >= STM_WIDTH
        and line.startswith("STR", cursor - ERROR_WIDTH)
    ):
        cursor -= ERROR_WIDTH
        count += 1
    return cursor if count else None


def parse_complete_line(line: str) -> dict[str, Any]:
    if len(line) < STM_WIDTH:
        raise ParseError("line is shorter than STM")
    stm = parse_stm(line[:STM_WIDTH])
    declared = stm["declared_length"]
    if declared > len(line):
        raise ParseError(
            f"STM declares {declared} characters but line contains {len(line)}"
        )

    # The guide defines STM length as all segments present in the message. Real
    # AGIRA rejection files therefore update it to include appended STR segments.
    # Older fixtures leave the echoed-message length unchanged, so accept both.
    content_ends = [declared]
    str_start = _trailing_str_start(line)
    if str_start is not None and declared == len(line):
        content_ends.insert(0, str_start)

    failures: list[ParseError] = []
    for content_end in dict.fromkeys(content_ends):
        content, tail = line[:content_end], line[content_end:]
        try:
            result = _parse_complete_content(content, stm)
        except ParseError as exc:
            failures.append(exc)
            continue
        errors, tail_warnings = _parse_str_tail(tail)
        result["errors"] = errors
        result["warnings"].extend(tail_warnings)
        result["physical_length"] = len(line)
        result["functional_message_length"] = content_end
        result["declared_length_scope"] = (
            "response_line_including_str"
            if tail and declared == len(line)
            else "functional_message"
        )
        return result

    raise failures[0]


def parse_functional_reply(line: str) -> dict[str, Any]:
    if not line.startswith("Q01"):
        raise ParseError("unsupported functional-only layout")
    if len(line) < Q01_WIDTH + min(Q00_WIDTHS):
        raise ParseError("functional-only line is too short")
    criteria = parse_q01(line[:Q01_WIDTH])
    q00_start = Q01_WIDTH
    q00_width = _q00_width_before(line, q00_start, "006")
    query_identification = parse_q00(line[q00_start : q00_start + q00_width])
    cursor = q00_start + q00_width
    matches: list[dict[str, Any]] = []
    while cursor + MATCH_WIDTH <= len(line) and line.startswith("006", cursor):
        matches.append(parse_match(line[cursor : cursor + MATCH_WIDTH]))
        cursor += MATCH_WIDTH
    warnings = [
        "functional-only compatibility layout: mandatory STM and STE/STD segments are absent",
        "segment order Q01 + Q00 + 006 is observed locally but is not a complete v3.1 AGIRA message",
    ]
    if q00_width == 72:
        warnings.append(
            "observed Q00 width is 72; the PDF field widths total 69 characters"
        )
    if cursor != len(line):
        warnings.append(f"{len(line) - cursor} trailing characters were not decoded")
    return {
        "layout": "functional_only_compatibility",
        "message_type": "FUNCTIONAL_REPLY",
        "physical_length": len(line),
        "criteria": criteria,
        "query_identification": query_identification,
        "matches": matches,
        "errors": [],
        "warnings": warnings,
    }


def parse_line(line: str) -> dict[str, Any]:
    if line.startswith("STM"):
        return parse_complete_line(line)
    if line.startswith("Q01"):
        return parse_functional_reply(line)
    raise ParseError(f"unsupported line prefix {line[:3]!r}")


def _build_conversations(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    conversations: list[dict[str, Any]] = []
    by_query_id: dict[str, dict[str, Any]] = {}
    for message in messages:
        message_type = message.get("message_type")
        query_identification = message.get("query_identification") or {}
        query_id = query_identification.get("company_query_identifier")
        if message_type == "AGQUES":
            conversation = {
                "query_id": query_id,
                "query": message,
                "results": [],
                "errors": message.get("errors", []),
            }
            conversations.append(conversation)
            if query_id:
                by_query_id[query_id] = conversation
        elif message_type == "AGREPO":
            conversation = by_query_id.get(query_id)
            if conversation is None:
                conversation = {
                    "query_id": query_id,
                    "query": None,
                    "results": [],
                    "errors": [],
                }
                conversations.append(conversation)
                if query_id:
                    by_query_id[query_id] = conversation
            conversation["results"].append(message)
            conversation["errors"].extend(message.get("errors", []))
        elif message_type == "FUNCTIONAL_REPLY":
            conversations.append(
                {
                    "query_id": query_id,
                    "query": {
                        "criteria": message.get("criteria"),
                        "layout": message.get("layout"),
                    },
                    "results": [
                        {
                            "matches": message.get("matches", []),
                            "record": None,
                            "layout": message.get("layout"),
                        }
                    ],
                    "errors": message.get("errors", []),
                }
            )
    return conversations


def parse_reply_bytes(
    payload: bytes,
    *,
    source_filename: str,
    encoding: str = "windows-1252",
    max_line_bytes: int = 8136,
) -> dict[str, Any]:
    try:
        text = payload.decode(encoding)
    except UnicodeDecodeError as exc:
        raise ParseError(f"file is not valid {encoding}: {exc}") from exc

    raw_lines = text.splitlines()
    messages: list[dict[str, Any]] = []
    file_errors: list[dict[str, Any]] = []
    warnings: list[str] = []
    for line_number, line in enumerate(raw_lines, start=1):
        if not line:
            warnings.append(f"line {line_number} is empty and was ignored")
            continue
        byte_length = len(line.encode(encoding))
        if byte_length > max_line_bytes:
            file_errors.append(
                {
                    "line": line_number,
                    "error": f"line is {byte_length} bytes; maximum is {max_line_bytes}",
                }
            )
            continue
        try:
            message = parse_line(line)
        except ParseError as exc:
            file_errors.append({"line": line_number, "error": str(exc)})
            continue
        message["line_number"] = line_number
        messages.append(message)
        warnings.extend(
            f"line {line_number}: {warning}" for warning in message.get("warnings", [])
        )

    return {
        "source_filename": source_filename,
        "encoding": encoding,
        "line_count": len(raw_lines),
        "message_count": len(messages),
        "warnings": warnings,
        "file_errors": file_errors,
        "conversations": _build_conversations(messages),
        "messages": messages,
    }
