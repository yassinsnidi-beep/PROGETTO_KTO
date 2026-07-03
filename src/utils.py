"""Shared utility functions for ingestion."""

from __future__ import annotations

import hashlib
import logging
import math
import re
from datetime import datetime, timezone
from typing import Any, Iterable

import pandas as pd

logger = logging.getLogger(__name__)


def utc_now_iso() -> str:
    """Return the current UTC timestamp as an ISO-8601 string."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def is_missing(value: Any) -> bool:
    """Return True for None, NaN, empty strings and pandas missing values."""
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    if isinstance(value, str) and not value.strip():
        return True
    return False


def clean_string(value: Any) -> str | None:
    """Normalize a scalar value to a stripped string or None."""
    if is_missing(value):
        return None
    text = str(value).strip()
    if re.fullmatch(r"\d+\.0", text):
        text = text[:-2]
    return text or None


def normalize_column_name(name: Any) -> str:
    """Normalize source column names for robust matching."""
    text = "" if name is None else str(name)
    text = text.lower().replace("\n", " ").replace("\r", " ")
    text = re.sub(r"[()]", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def safe_float(value: Any, default: float | None = None) -> float | None:
    """Parse badly formatted numeric values into float."""
    if is_missing(value):
        return default
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if math.isnan(float(value)) or math.isinf(float(value)):
            return default
        return float(value)
    text = str(value).strip()
    if not text:
        return default
    text = text.replace("\u00a0", "").replace(" ", "")
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    else:
        text = text.replace(",", ".")
    text = re.sub(r"[^0-9.+-]", "", text)
    try:
        return float(text)
    except ValueError:
        logger.warning("Could not parse float value: %r", value)
        return default


def safe_int(value: Any, default: int | None = None) -> int | None:
    """Parse a value into int, accepting formatted floats."""
    parsed = safe_float(value, None)
    if parsed is None:
        return default
    return int(round(parsed))


def stable_hash(value: str, length: int = 16) -> str:
    """Return a stable hexadecimal hash for deterministic fallback IDs."""
    return hashlib.sha1(value.strip().lower().encode("utf-8")).hexdigest()[:length]


def join_non_empty(lines: Iterable[tuple[str, Any]]) -> str:
    """Join labelled values, skipping missing values."""
    output: list[str] = []
    for label, value in lines:
        if is_missing(value):
            continue
        if isinstance(value, list):
            value = "; ".join(str(item) for item in value if not is_missing(item))
        value_text = clean_string(value)
        if value_text:
            output.append(f"{label}: {value_text}")
    return "\n".join(output)
