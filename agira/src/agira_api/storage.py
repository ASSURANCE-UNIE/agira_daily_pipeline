from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .fixed_width import safe_filename


def resolve_child(directory: Path, filename: str) -> Path:
    safe = safe_filename(filename)
    directory = directory.resolve()
    candidate = (directory / safe).resolve()
    if candidate.parent != directory:
        raise ValueError("path escapes the configured directory")
    return candidate


def atomic_write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    payload = (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False) + "\n"
    ).encode("utf-8")
    atomic_write_bytes(path, payload)

