from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .fixed_width import SerializationError
from .parser import ParseError
from .service import AgiraDocumentKind, agira_to_json, json_to_agira
from .storage import atomic_write_bytes, atomic_write_json


KINDS: tuple[AgiraDocumentKind, ...] = (
    "raw",
    "questions",
    "responses",
    "termination-requests",
    "termination-responses",
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agira-translate",
        description="Translate JSON to AGIRA RA TXT and AGIRA files to JSON.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    to_agira = subparsers.add_parser("to-agira", help="business JSON -> AGIRA TXT")
    to_agira.add_argument("source", type=Path)
    to_agira.add_argument("--output", type=Path)
    to_agira.add_argument("--encoding", default="windows-1252")
    to_agira.add_argument("--overwrite", action="store_true")

    to_json = subparsers.add_parser("to-json", help="AGIRA file -> readable JSON")
    to_json.add_argument("source", type=Path)
    to_json.add_argument("--output", type=Path)
    to_json.add_argument("--kind", choices=KINDS, default="raw")
    to_json.add_argument("--encoding", default="windows-1252")
    to_json.add_argument("--overwrite", action="store_true")
    return parser


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("the source JSON document must be an object")
    return value


def _refuse_overwrite(path: Path, *, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(
            f"refusing to overwrite {path}; pass --overwrite for this exact file"
        )


def run(arguments: argparse.Namespace) -> Path:
    source = arguments.source.resolve()
    if arguments.command == "to-agira":
        rendered = json_to_agira(_read_json(source), encoding=arguments.encoding)
        output = (arguments.output or source.with_name(rendered.filename)).resolve()
        _refuse_overwrite(output, overwrite=arguments.overwrite)
        atomic_write_bytes(output, rendered.payload)
        return output

    output = (arguments.output or source.with_suffix(".json")).resolve()
    _refuse_overwrite(output, overwrite=arguments.overwrite)
    translated = agira_to_json(
        source.read_bytes(),
        source_filename=source.name,
        kind=arguments.kind,
        encoding=arguments.encoding,
    )
    atomic_write_json(output, translated)
    return output


def main() -> None:
    parser = _parser()
    try:
        output = run(parser.parse_args())
    except (
        FileNotFoundError,
        FileExistsError,
        json.JSONDecodeError,
        UnicodeError,
        ValidationError,
        SerializationError,
        ParseError,
        ValueError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    print(output)


if __name__ == "__main__":
    main()
