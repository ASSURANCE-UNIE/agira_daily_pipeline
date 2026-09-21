from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import ValidationError

from .config import PipelineConfig
from .runner import run_feed


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agira-daily",
        description="Extract, validate, archive, and publish daily AGIRA files.",
    )
    parser.add_argument(
        "feed",
        choices=("questions", "terminations", "all"),
        help="feed to run",
    )
    parser.add_argument(
        "--settings",
        type=Path,
        default=Path("settings.toml"),
    )
    parser.add_argument(
        "--run-date",
        type=date.fromisoformat,
        help="processing date (YYYY-MM-DD); defaults to today in configured timezone",
    )
    parser.add_argument(
        "--input-json",
        type=Path,
        help="development/test array of query-result rows; only with one feed",
    )
    return parser


def _rows(path: Path | None) -> list[dict[str, Any]] | None:
    if path is None:
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError("--input-json must contain an array of JSON objects")
    return value


def main() -> None:
    arguments = _parser().parse_args()
    try:
        config = PipelineConfig.load(arguments.settings)
        run_date = arguments.run_date or datetime.now(
            ZoneInfo(config.timezone)
        ).date()
        rows = _rows(arguments.input_json)
        if arguments.feed == "all" and rows is not None:
            raise ValueError("--input-json cannot be combined with feed 'all'")
        feeds = (
            ("questions", "terminations")
            if arguments.feed == "all"
            else (arguments.feed,)
        )
        for feed in feeds:
            publication = run_feed(
                feed,
                config=config,
                run_date=run_date,
                rows=rows,
            )
            destination = publication.depot_path or publication.history_dir
            print(f"{feed}: {publication.status}: {destination}")
    except (
        FileNotFoundError,
        FileExistsError,
        json.JSONDecodeError,
        RuntimeError,
        ValidationError,
        ValueError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
