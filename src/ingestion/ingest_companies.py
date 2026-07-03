"""Ingest AIDA company Excel exports into MongoDB-ready documents."""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd
from pydantic import ValidationError

from src.embedding_service import EmbeddingService
from src.models import CompanyDocument
from src.utils import clean_string, is_missing, join_non_empty, safe_float, safe_int, utc_now_iso
from src.ingestion.mapping import COMPANY_COLUMN_ALIASES, map_province_to_region, rename_columns
from src.ingestion.metrics import compute_raw_company_metrics, normalize_company_metrics
from src.ingestion.normalization import (
    normalize_ateco_code,
    normalize_nace_code,
    normalize_tax_code,
    normalized_name,
)

logger = logging.getLogger(__name__)


def build_company_embedding_texts(row: dict[str, Any]) -> dict[str, str]:
    """Build Italian and English embedding texts for a company."""
    return {
        "it": join_non_empty(
            [
                ("Nome azienda", row.get("company_name")),
                ("Descrizione attivita IT", row.get("trade_description_it")),
            ]
        ),
        "en": join_non_empty(
            [
                ("Company name", row.get("company_name")),
                ("Business description EN", row.get("trade_description_gb")),
            ]
        ),
    }


def _company_document_from_row(row: dict[str, Any], embedding_service: EmbeddingService) -> dict[str, Any] | None:
    company_name = clean_string(row.get("company_name"))
    tax_code, has_tax_code = normalize_tax_code(row.get("tax_code"), company_name)
    if not tax_code:
        logger.error("Skipping company without tax code and fallback name: %r", row)
        return None

    now = utc_now_iso()
    province = clean_string(row.get("province"))
    nace_code = normalize_nace_code(row.get("nace_code"))
    ateco_2007_code = normalize_ateco_code(row.get("ateco_2007_code"))
    ateco_2002_code = normalize_ateco_code(row.get("ateco_2002_code"))
    revenues = safe_float(row.get("revenues_th_eur"), None)
    employees = safe_int(row.get("employees"), None)
    rnd_values = {
        "last_available_year": safe_float(row.get("rnd_last_year_th_eur"), 0.0) or 0.0,
        "year_minus_1": safe_float(row.get("rnd_year_minus_1_th_eur"), 0.0) or 0.0,
        "year_minus_2": safe_float(row.get("rnd_year_minus_2_th_eur"), 0.0) or 0.0,
        "year_minus_3": safe_float(row.get("rnd_year_minus_3_th_eur"), 0.0) or 0.0,
    }
    data_quality = {
        "has_tax_code": has_tax_code,
        "has_nace_code": bool(nace_code),
        "has_ateco_2007_code": bool(ateco_2007_code),
        "has_trade_description_it": not is_missing(row.get("trade_description_it")),
        "has_trade_description_gb": not is_missing(row.get("trade_description_gb")),
        "has_revenues": revenues is not None,
        "has_employees": employees is not None,
        "has_rnd_data": any(value > 0 for value in rnd_values.values()),
    }
    metrics = compute_raw_company_metrics(row)
    metrics["data_quality_score"] = sum(data_quality.values()) / len(data_quality)
    embedding_texts = build_company_embedding_texts(row)
    document = {
        "_id": f"company:{tax_code}",
        "source": "AIDA",
        "company_name": company_name,
        "normalized_name": normalized_name(company_name),
        "tax_code": tax_code,
        "cciaa_number": clean_string(row.get("cciaa_number")),
        "location": {
            "province": province,
            "region": map_province_to_region(province),
            "country": "Italy",
        },
        "industry_classification": {
            "nace_rev_2": {
                "raw_code": clean_string(row.get("nace_code")),
                "code": nace_code,
                "division": nace_code.split(".")[0] if nace_code else None,
                "description": clean_string(row.get("nace_description")),
            },
            "ateco_2007": {
                "raw_code": clean_string(row.get("ateco_2007_code")),
                "code": ateco_2007_code,
                "description": clean_string(row.get("ateco_2007_description")),
            },
            "ateco_2002": {
                "raw_code": clean_string(row.get("ateco_2002_code")),
                "code": ateco_2002_code,
                "description": clean_string(row.get("ateco_2002_description")),
            },
        },
        "business_profile": {
            "trade_description_it": clean_string(row.get("trade_description_it")),
            "trade_description_gb": clean_string(row.get("trade_description_gb")),
        },
        "embeddings": {
            "it": {"text": embedding_texts["it"], "vector": [], "model": None},
            "en": {"text": embedding_texts["en"], "vector": [], "model": None},
        },
        "financials": {
            "accounting_closing_date": clean_string(row.get("accounting_closing_date")),
            "revenues_th_eur": revenues,
            "employees": employees,
            "rnd_expenses_th_eur": rnd_values,
        },
        "metrics": metrics,
        "data_quality": data_quality,
        "created_at": now,
        "updated_at": now,
    }
    return embedding_service.add_embeddings_to_document(document)


def build_company_documents(
    path: str,
    embedding_service: EmbeddingService,
    sheet_name: str = "Results",
    limit: int | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Read the company Excel file and return validated MongoDB documents."""
    frame = pd.read_excel(path, sheet_name=sheet_name, dtype=object)
    if limit:
        frame = frame.head(limit)
    rows = rename_columns(frame.to_dict(orient="records"), COMPANY_COLUMN_ALIASES)
    raw_documents: list[dict[str, Any]] = []
    errors = 0
    for row in rows:
        document = _company_document_from_row(row, embedding_service)
        if document is None:
            errors += 1
            continue
        raw_documents.append(document)

    normalize_company_metrics(raw_documents)
    documents: list[dict[str, Any]] = []
    for document in raw_documents:
        document["metrics"]["data_quality_score"] = sum(document["data_quality"].values()) / len(document["data_quality"])
        try:
            model = CompanyDocument.model_validate(document)
            documents.append(model.model_dump(by_alias=True))
        except ValidationError:
            errors += 1
            logger.exception("Invalid company document skipped: %s", document.get("_id"))
    return documents, {"read": len(rows), "valid": len(documents), "errors": errors}
