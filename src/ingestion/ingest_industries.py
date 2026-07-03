"""Ingest NACE industry CSV files into MongoDB-ready documents."""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd
from pydantic import ValidationError

from src.embedding_service import EmbeddingService
from src.models import IndustryDocument
from src.utils import clean_string, join_non_empty, utc_now_iso
from src.ingestion.normalization import normalize_nace_code

logger = logging.getLogger(__name__)


def build_industry_embedding_texts(row: dict[str, Any]) -> dict[str, str]:
    """Build Italian and English embedding texts for one NACE class."""
    code = row.get("code")
    return {
        "it": join_non_empty(
            [
                ("Codice NACE", code),
                ("Classe", row.get("class_label_it")),
                ("Gruppo", row.get("group_label_it")),
                ("Divisione", row.get("division_label_it")),
                ("Sezione", row.get("section_label_it")),
            ]
        ),
        "en": join_non_empty(
            [
                ("NACE code", code),
                ("Class", row.get("class_label_en")),
                ("Group", row.get("group_label_en")),
                ("Division", row.get("division_label_en")),
                ("Section", row.get("section_label_en")),
            ]
        ),
    }


def _industry_document_from_row(row: dict[str, Any], embedding_service: EmbeddingService) -> dict[str, Any] | None:
    raw_code = clean_string(row.get("class"))
    code = normalize_nace_code(raw_code)
    if not code:
        logger.error("Skipping industry without valid NACE class code: %r", row)
        return None
    row = {**row, "code": code}
    now = utc_now_iso()
    texts = build_industry_embedding_texts(row)
    group_code = normalize_nace_code(row.get("group"))
    document = {
        "_id": f"industry:nace:{code}",
        "source": "NACE",
        "system": "NACE Rev. 2",
        "code": code,
        "raw_code": raw_code,
        "level": "class",
        "labels": {
            "it": {
                "class": clean_string(row.get("class_label_it")),
                "group": clean_string(row.get("group_label_it")),
                "division": clean_string(row.get("division_label_it")),
                "section": clean_string(row.get("section_label_it")),
            },
            "en": {
                "class": clean_string(row.get("class_label_en")),
                "group": clean_string(row.get("group_label_en")),
                "division": clean_string(row.get("division_label_en")),
                "section": clean_string(row.get("section_label_en")),
            },
        },
        "group": {
            "code": group_code,
            "label_it": clean_string(row.get("group_label_it")),
            "label_en": clean_string(row.get("group_label_en")),
        },
        "division": {
            "code": clean_string(row.get("division")),
            "label_it": clean_string(row.get("division_label_it")),
            "label_en": clean_string(row.get("division_label_en")),
        },
        "section": {
            "code": clean_string(row.get("section")),
            "label_it": clean_string(row.get("section_label_it")),
            "label_en": clean_string(row.get("section_label_en")),
        },
        "embeddings": {
            "it": {"text": texts["it"], "vector": [], "model": None},
            "en": {"text": texts["en"], "vector": [], "model": None},
        },
        "created_at": now,
        "updated_at": now,
    }
    return embedding_service.add_embeddings_to_document(document)


def build_industry_documents(
    path: str,
    embedding_service: EmbeddingService,
    limit: int | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Read a NACE CSV file and return validated MongoDB documents."""
    frame = pd.read_csv(path, dtype=object)
    if limit:
        frame = frame.head(limit)
    records = frame.to_dict(orient="records")
    documents: list[dict[str, Any]] = []
    errors = 0
    for row in records:
        document = _industry_document_from_row(row, embedding_service)
        if document is None:
            errors += 1
            continue
        try:
            model = IndustryDocument.model_validate(document)
            documents.append(model.model_dump(by_alias=True))
        except ValidationError:
            errors += 1
            logger.exception("Invalid industry document skipped: %s", document.get("_id"))
    return documents, {"read": len(records), "valid": len(documents), "errors": errors}
