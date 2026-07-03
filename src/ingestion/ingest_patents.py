"""Ingest UNIBO patent Excel files into MongoDB-ready documents."""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd
from pydantic import ValidationError

from src.embedding_service import EmbeddingService
from src.models import PatentDocument
from src.utils import clean_string, is_missing, join_non_empty, utc_now_iso
from src.ingestion.mapping import PATENT_COLUMN_ALIASES, rename_columns
from src.ingestion.normalization import extract_trl, split_text_list

logger = logging.getLogger(__name__)


def build_patent_embedding_texts(row: dict[str, Any]) -> dict[str, str]:
    """Build Italian patent embedding text; English is left empty unless provided later."""
    return {
        "it": join_non_empty(
            [
                ("Titolo", row.get("title")),
                ("Sottotitolo", row.get("subtitle")),
                ("Abstract", row.get("abstract")),
                ("Descrizione breve", row.get("short_description")),
                ("Descrizione completa", row.get("full_description")),
                ("Vantaggi", row.get("advantages")),
                ("Applicazioni", row.get("applications")),
                ("Stadio sviluppo", row.get("development_stage")),
                ("Tipo protezione", row.get("protection_type")),
                ("Stato brevetto", row.get("patent_status")),
            ]
        ),
        "en": "",
    }


def _patent_document_from_row(row: dict[str, Any], embedding_service: EmbeddingService) -> dict[str, Any] | None:
    scheda_id = clean_string(row.get("scheda_id"))
    if not scheda_id:
        logger.error("Skipping patent without scheda_id: %r", row)
        return None
    advantages = split_text_list(row.get("advantages"))
    applications = split_text_list(row.get("applications"))
    normalized_row = {
        **row,
        "advantages": advantages,
        "applications": applications,
    }
    now = utc_now_iso()
    texts = build_patent_embedding_texts(normalized_row)
    document = {
        "_id": f"patent:unibo:{scheda_id}",
        "source": "UNIBO",
        "scheda_id": scheda_id,
        "title": clean_string(row.get("title")),
        "subtitle": clean_string(row.get("subtitle")),
        "url": clean_string(row.get("url")),
        "abstract": clean_string(row.get("abstract")),
        "short_description": clean_string(row.get("short_description")),
        "full_description": clean_string(row.get("full_description")),
        "advantages": advantages,
        "applications": applications,
        "development_stage": clean_string(row.get("development_stage")),
        "trl": extract_trl(row.get("development_stage")),
        "protection_type": clean_string(row.get("protection_type")),
        "patent_status": clean_string(row.get("patent_status")),
        "patent_number": clean_string(row.get("patent_number")),
        "application_number": clean_string(row.get("application_number")),
        "kto": {
            "contact_name": clean_string(row.get("kto_contact_name")),
            "email": clean_string(row.get("kto_contact_email")),
            "phone": clean_string(row.get("kto_contact_phone")),
        },
        "embeddings": {
            "it": {"text": texts["it"], "vector": [], "model": None},
            "en": {"text": texts["en"], "vector": [], "model": None},
        },
        "data_quality": {
            "has_title": not is_missing(row.get("title")),
            "has_abstract": not is_missing(row.get("abstract")),
            "has_full_description": not is_missing(row.get("full_description")),
            "has_applications": bool(applications),
            "has_advantages": bool(advantages),
        },
        "created_at": now,
        "updated_at": now,
    }
    return embedding_service.add_embeddings_to_document(document)


def build_patent_documents(
    path: str,
    embedding_service: EmbeddingService,
    sheet_name: str = "Brevetti",
    limit: int | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Read the patent Excel file and return validated MongoDB documents."""
    frame = pd.read_excel(path, sheet_name=sheet_name, dtype=object)
    if limit:
        frame = frame.head(limit)
    rows = rename_columns(frame.to_dict(orient="records"), PATENT_COLUMN_ALIASES)
    documents: list[dict[str, Any]] = []
    errors = 0
    for row in rows:
        document = _patent_document_from_row(row, embedding_service)
        if document is None:
            errors += 1
            continue
        try:
            model = PatentDocument.model_validate(document)
            documents.append(model.model_dump(by_alias=True))
        except ValidationError:
            errors += 1
            logger.exception("Invalid patent document skipped: %s", document.get("_id"))
    return documents, {"read": len(rows), "valid": len(documents), "errors": errors}
