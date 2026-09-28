from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agira_api.parser import ParseError

from .config import PipelineConfig
from .inbound import archive_inbound_file, discover_inbound_files


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agira-inbound",
        description="Translate and archive AGIRA response and rejection files.",
    )
    parser.add_argument(
        "--settings",
        type=Path,
        default=Path("settings.toml"),
    )
    parser.add_argument("--encoding", default="windows-1252")
    return parser


def main() -> None:
    arguments = _parser().parse_args()
    try:
        config = PipelineConfig.load(arguments.settings)
        sources = discover_inbound_files(config.depot)
    except (FileNotFoundError, KeyError, TypeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

    if not sources:
        print("no AGIRA inbound files found")
        return

    failures: list[tuple[Path, Exception]] = []
    for source in sources:
        try:
            result = archive_inbound_file(
                source,
                history_root=config.history,
                encoding=arguments.encoding,
            )
        except (
            FileNotFoundError,
            FileExistsError,
            OSError,
            UnicodeError,
            json.JSONDecodeError,
            ParseError,
            ValueError,
        ) as exc:
            failures.append((source, exc))
            print(f"error: {source.name}: {exc}", file=sys.stderr)
            continue
        print(
            f"{result.status}: {result.category}: "
            f"{result.source_path.name} -> {result.json_path}; depot source removed"
        )

    if failures:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
