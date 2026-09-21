from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Iterable, Mapping

from agira_api.models import (
    Emitter,
    MonthYearDate,
    QueryCriteria,
    Question,
    QuestionBatch,
)


def _text(value: Any) -> str | None:
    if value is None:
        return None
    rendered = str(value).strip()
    return rendered or None


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {
        "1",
        "true",
        "t",
        "oui",
        "o",
        "yes",
        "y",
    }


def _date(value: Any, *, field: str, row_number: int) -> date | None:
    text = _text(value)
    if text is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    for pattern in ("%Y-%m-%d", "%d%m%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            pass
    raise ValueError(f"row {row_number}: {field} has unsupported date {text!r}")


def _probes(row: Mapping[str, Any], row_number: int) -> list[tuple[str, dict[str, Any]]]:
    legal = _truthy(row.get("est_personne_morale"))
    name = _text(row.get("nom"))
    first_name = None if legal else _text(row.get("prenom"))
    birth_date = None if legal else _date(
        row.get("date_naissance"), field="date_naissance", row_number=row_number
    )
    licence_date = None if legal else _date(
        row.get("permis_date_obtention"),
        field="permis_date_obtention",
        row_number=row_number,
    )
    postal_code = _text(row.get("code_postal"))
    if postal_code and len(postal_code) != 5:
        raise ValueError(f"row {row_number}: code_postal must contain exactly 5 characters")
    registration = _text(row.get("immatriculation"))
    siren = _text(row.get("siren"))
    previous_insurer = _text(row.get("previous_insurer_company_code"))
    previous_contract = _text(row.get("previous_contract_number"))

    probes: list[tuple[str, dict[str, Any]]] = []
    if name and first_name and postal_code:
        probes.append(("01", {
            "last_name_or_company_name": name,
            "first_name": first_name,
            "residence_postal_code": postal_code,
        }))
    if previous_insurer and previous_contract:
        probes.append(("02", {
            "previous_insurer_company_code": previous_insurer,
            "contract_number": previous_contract,
        }))
    if name and len(name) >= 5 and birth_date and postal_code:
        probes.append(("03", {
            "last_name_or_company_name": name[:5],
            "birth_date": birth_date,
            "residence_postal_code": postal_code,
        }))
    if name and birth_date:
        probes.append(("04", {
            "last_name_or_company_name": name,
            "birth_date": MonthYearDate(month=birth_date.month, year=birth_date.year),
        }))
    if name and first_name and licence_date:
        probes.append(("05", {
            "last_name_or_company_name": name,
            "first_name": first_name,
            "driving_licence_date": licence_date,
        }))
    if name and len(name) >= 5 and licence_date and postal_code:
        probes.append(("06", {
            "last_name_or_company_name": name[:5],
            "driving_licence_date": licence_date,
            "residence_postal_code": postal_code,
        }))
    if registration:
        probes.append(("07", {"registration_number": registration}))
    if siren:
        probes.append(("08", {"siren": siren}))
    return probes


def _policy_part(value: Any, row_number: int) -> str:
    raw = (_text(value) or f"ROW{row_number:06d}").upper()
    sanitized = re.sub(r"[^A-Z0-9]+", "-", raw).strip("-")
    return (sanitized or f"ROW{row_number:06d}")[:20]


def build_question_batch(
    rows: Iterable[Mapping[str, Any]],
    *,
    environment: str,
    account_code: str,
    sequence: int,
    emitter: Emitter,
    emitted_at: datetime,
) -> QuestionBatch:
    questions: list[Question] = []
    for row_number, original in enumerate(rows, start=1):
        row = {str(key).strip().lower(): value for key, value in original.items()}
        probes = _probes(row, row_number)
        if not probes:
            raise ValueError(
                f"row {row_number}: no AGIRA correspondence family can be built"
            )
        policy = _policy_part(row.get("numero_police"), row_number)
        for family, values in probes:
            query_id = f"{policy}-{emitted_at:%Y%m%d}-{row_number:06d}-C{family}"
            questions.append(
                Question(query_id=query_id, criteria=QueryCriteria(**values))
            )
    if not questions:
        raise ValueError("cannot build an AGIRA question batch with no questions")
    return QuestionBatch(
        environment=environment,
        account_code=account_code,
        sequence=sequence,
        emitter=emitter,
        questions=questions,
        emitted_at=emitted_at,
    )
