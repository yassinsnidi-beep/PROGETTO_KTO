"""Normalization helpers for source data."""

from __future__ import annotations

import re
from typing import Any

from src.utils import clean_string, is_missing, stable_hash


def normalize_code_digits(value: Any) -> str | None:
    """Return only digits from a code-like value, preserving strings when possible."""
    text = clean_string(value)
    if not text:
        return None
    if re.fullmatch(r"\d+\.0", text):
        text = text[:-2]
    digits = re.sub(r"\D", "", text)
    return digits or None


def normalize_nace_code(value: Any) -> str | None:
    """Normalize NACE class codes such as 2829 to 28.29."""
    text = clean_string(value)
    if not text:
        return None
    if "." in text:
        parts = [part for part in re.split(r"\D+", text) if part]
        if len(parts) >= 2:
            return f"{parts[0].zfill(2)}.{parts[1].zfill(2)}"
        if len(parts) == 1:
            text = parts[0]
    digits = normalize_code_digits(text)
    if not digits:
        return None
    if len(digits) >= 4:
        return f"{digits[:2]}.{digits[2:4]}"
    if len(digits) == 2:
        return digits
    return digits


def normalize_ateco_code(value: Any) -> str | None:
    """Normalize ATECO codes such as 282930 to 28.29.30."""
    text = clean_string(value)
    if not text:
        return None
    if "." in text:
        parts = [part for part in re.split(r"\D+", text) if part]
        if len(parts) >= 3:
            return f"{parts[0].zfill(2)}.{parts[1].zfill(2)}.{parts[2].zfill(2)}"
        if len(parts) == 2:
            return f"{parts[0].zfill(2)}.{parts[1].zfill(2)}"
    digits = normalize_code_digits(text)
    if not digits:
        return None
    if len(digits) >= 6:
        return f"{digits[:2]}.{digits[2:4]}.{digits[4:6]}"
    if len(digits) >= 4:
        return f"{digits[:2]}.{digits[2:4]}"
    return digits


def normalize_tax_code(value: Any, company_name: Any = None) -> tuple[str | None, bool]:
    """Normalize tax code and create a deterministic fallback when missing."""
    text = clean_string(value)
    if text:
        normalized = re.sub(r"\s+", "", text.upper())
        if re.fullmatch(r"\d+", normalized) and len(normalized) < 11:
            normalized = normalized.zfill(11)
        return normalized, True
    name = clean_string(company_name)
    if not name:
        return None, False
    return f"missing:{stable_hash(name)}", False


def normalized_name(value: Any) -> str | None:
    """Return a normalized company name for matching and display."""
    text = clean_string(value)
    if not text:
        return None
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip() or None


def split_text_list(value: Any) -> list[str]:
    """Split bullets, newlines and semicolon-separated long text into a clean list."""
    text = clean_string(value)
    if not text:
        return []
    pieces = re.split(r"(?:\r?\n|;|•|\u2022|\s+-\s+)", text)
    cleaned: list[str] = []
    seen: set[str] = set()
    for piece in pieces:
        item = re.sub(r"\s+", " ", piece).strip(" .;-")
        if len(item) < 3:
            continue
        key = item.lower()
        if key not in seen:
            cleaned.append(item)
            seen.add(key)
    if not cleaned and not is_missing(text):
        return [text]
    return cleaned


def extract_trl(*values: Any) -> int | None:
    """Extract a TRL value from development-stage text."""
    for value in values:
        text = clean_string(value)
        if not text:
            continue
        match = re.search(r"\btrl\s*[:\-]?\s*([1-9])\b", text, flags=re.IGNORECASE)
        if match:
            return int(match.group(1))
        match = re.search(r"\b([1-9])\b", text)
        if match:
            return int(match.group(1))
    return None
