from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Literal

from agira_api import json_to_agira
from agira_api.models import QuestionBatch, TerminationBatch
from agira_api.storage import atomic_write_bytes, atomic_write_json


Feed = Literal["questions", "terminations"]


@dataclass(frozen=True, slots=True)
class Publication:
    feed: Feed
    run_date: date
    source_date: date
    history_dir: Path
    json_path: Path | None
    txt_path: Path | None
    depot_path: Path | None
    status: Literal["published", "empty"]


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def publish_batch(
    batch: QuestionBatch | TerminationBatch,
    *,
    feed: Feed,
    run_date: date,
    source_date: date,
    source_row_count: int,
    history_root: Path,
    depot_root: Path,
) -> Publication:
    day_dir = history_root / feed / run_date.isoformat()
    if day_dir.exists():
        raise FileExistsError(f"history already exists for {feed} on {run_date}")
    document = batch.model_dump(mode="json", exclude_none=True)
    rendered = json_to_agira(document)
    depot_path = depot_root / feed / rendered.filename
    if depot_path.exists():
        raise FileExistsError(f"depot file already exists: {depot_path}")

    json_name = f"{feed}.json"
    day_dir.mkdir(parents=True)
    json_path = day_dir / json_name
    txt_path = day_dir / rendered.filename
    atomic_write_json(json_path, document)
    atomic_write_bytes(txt_path, rendered.payload)
    atomic_write_json(
        day_dir / "manifest.json",
        {
            "status": "published",
            "feed": feed,
            "run_date": run_date.isoformat(),
            "source_date": source_date.isoformat(),
            "source_row_count": source_row_count,
            "agira_item_count": rendered.item_count,
            "json_filename": json_name,
            "json_sha256": _sha256(
                (json.dumps(document, ensure_ascii=False, indent=2) + "\n").encode(
                    "utf-8"
                )
            ),
            "txt_filename": rendered.filename,
            "txt_sha256": rendered.sha256,
            "published_at_utc": datetime.now(timezone.utc).isoformat(),
        },
    )
    atomic_write_bytes(depot_path, rendered.payload)
    return Publication(
        feed=feed,
        run_date=run_date,
        source_date=source_date,
        history_dir=day_dir,
        json_path=json_path,
        txt_path=txt_path,
        depot_path=depot_path,
        status="published",
    )


def publish_empty(
    *,
    feed: Feed,
    run_date: date,
    source_date: date,
    history_root: Path,
) -> Publication:
    day_dir = history_root / feed / run_date.isoformat()
    if day_dir.exists():
        raise FileExistsError(f"history already exists for {feed} on {run_date}")
    day_dir.mkdir(parents=True)
    atomic_write_json(
        day_dir / "manifest.json",
        {
            "status": "empty",
            "feed": feed,
            "run_date": run_date.isoformat(),
            "source_date": source_date.isoformat(),
            "source_row_count": 0,
            "agira_item_count": 0,
            "reason": "query returned no rows; no invalid empty AGIRA file was created",
            "published_at_utc": datetime.now(timezone.utc).isoformat(),
        },
    )
    return Publication(
        feed=feed,
        run_date=run_date,
        source_date=source_date,
        history_dir=day_dir,
        json_path=None,
        txt_path=None,
        depot_path=None,
        status="empty",
    )
