from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import MonthYearDate


class SerializationError(ValueError):
    """Raised when a value cannot be represented in the AGIRA layout."""


_CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]")


def normalize_text(value: object | None) -> str:
    if value is None:
        return ""
    normalized = unicodedata.normalize("NFC", str(value)).strip().upper()
    if _CONTROL_CHARACTERS.search(normalized):
        raise SerializationError("control characters are not allowed")
    return normalized


def an(value: object | None, width: int, *, encoding: str) -> str:
    normalized = normalize_text(value)
    try:
        encoded = normalized.encode(encoding)
    except UnicodeEncodeError as exc:
        raise SerializationError(
            f"value {normalized!r} is not representable in {encoding}"
        ) from exc
    if len(encoded) > width:
        raise SerializationError(
            f"value {normalized!r} uses {len(encoded)} bytes; maximum is {width}"
        )
    return normalized + (" " * (width - len(encoded)))


def digits(
    value: object | None,
    width: int,
    *,
    required: bool = False,
    zero_pad: bool = False,
) -> str:
    if value is None or str(value).strip() == "":
        if required:
            raise SerializationError(f"a {width}-digit value is required")
        return " " * width
    text = str(value).strip()
    if not text.isdigit():
        raise SerializationError(f"expected digits, received {text!r}")
    if len(text) > width:
        raise SerializationError(f"numeric value {text!r} exceeds width {width}")
    if zero_pad:
        return text.zfill(width)
    if len(text) != width:
        raise SerializationError(f"expected exactly {width} digits, received {text!r}")
    return text


def ddmmyyyy(value: date | MonthYearDate | None) -> str:
    if value is None:
        return " " * 8
    if isinstance(value, date):
        return value.strftime("%d%m%Y")
    return f"00{value.month:02d}{value.year:04d}"  # partial date, day 00


def yyyymmddhhmmss(value: datetime) -> str:
    return value.strftime("%Y%m%d%H%M%S")


def safe_filename(filename: str) -> str:
    if not filename or filename in {".", ".."}:
        raise ValueError("invalid filename")
    if "/" in filename or "\\" in filename:
        raise ValueError("filename must not contain a path")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", filename):
        raise ValueError("filename contains unsupported characters")
    return filename

