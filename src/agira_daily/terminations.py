from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Iterable, Mapping

from agira_api.models import Emitter, TerminationBatch, TerminationRecord


def _record_document(row: Mapping[str, Any], row_number: int) -> Mapping[str, Any]:
    lowered = {str(key).strip().lower(): value for key, value in row.items()}
    if "record_json" in lowered:
        value = lowered["record_json"]
        if isinstance(value, str):
            value = json.loads(value)
        if not isinstance(value, Mapping):
            raise ValueError(f"row {row_number}: record_json must decode to an object")
        return value
    if "operation" in row and "record_company" in row:
        return row
    raise ValueError(
        f"row {row_number}: termination query must return a record_json column"
    )


def build_termination_batch(
    rows: Iterable[Mapping[str, Any]],
    *,
    environment: str,
    account_code: str,
    sequence: int,
    emitter: Emitter,
    emitted_at: datetime,
) -> TerminationBatch:
    records = [
        TerminationRecord.model_validate(_record_document(row, row_number))
        for row_number, row in enumerate(rows, start=1)
    ]
    if not records:
        raise ValueError("cannot build an AGIRA termination batch with no records")
    return TerminationBatch(
        environment=environment,
        account_code=account_code,
        sequence=sequence,
        emitter=emitter,
        records=records,
        emitted_at=emitted_at,
    )
