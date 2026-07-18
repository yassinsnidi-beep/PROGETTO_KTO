"""Ingest AIDA company Excel exports into MongoDB-ready documents."""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd
from pydantic import ValidationError

from src.embedding_service import EmbeddingService
from src.models import CompanyDocument
from src.utils import clean_string, is_missing, join_non_empty, safe_float, safe_int, utc_now_iso, normalize_column_name
from src.ingestion.mapping import COMPANY_COLUMN_ALIASES, map_province_to_region, rename_columns
from src.ingestion.metrics import compute_raw_company_metrics, normalize_company_metrics
from src.ingestion.normalization import (
    normalize_ateco_code,
    normalize_nace_code,
    normalize_tax_code,
    normalized_name,
)

logger = logging.getLogger(__name__)


def _is_english_column(col_name: str) -> bool:
    """Classify column language based on AIDA header conventions."""
    name_lower = col_name.lower()
    if any(x in name_lower for x in ["(gb)", "(en)", "english", "uk", "us", "naics", "sic"]):
        return True
    english_fields = [
        "full overview", "history", "primary business line", "secondary business line",
        "main activity", "secondary activity", "main products and services",
        "strategy, organization and policy", "strategic alliances", "peer group description",
        "size estimate", "membership of a network", "main brand names", "main customers"
    ]
    if any(field in name_lower for field in english_fields):
        return True
    return False


def build_company_embedding_texts_dynamic(row: dict[str, Any], active_cols: list[str]) -> dict[str, str]:
    """Build dynamic Italian and English embedding texts using enabled columns."""
    it_lines = []
    en_lines = []
    
    for col in active_cols:
        normalized_col = normalize_column_name(col)
        field_name = None
        for field, aliases_list in COMPANY_COLUMN_ALIASES.items():
            if any(normalize_column_name(a) == normalized_col for a in aliases_list):
                field_name = field
                break
        if not field_name:
            field_name = f"custom_{normalized_col}"
            
        val = row.get(field_name)
        if is_missing(val):
            continue
            
        val_str = clean_string(val)
        if not val_str:
            continue
            
        if _is_english_column(col):
            en_lines.append((col, val_str))
        else:
            it_lines.append((col, val_str))
            
    company_name = row.get("company_name") or "N/A"
    return {
        "it": join_non_empty([("Nome azienda", company_name)] + it_lines),
        "en": join_non_empty([("Company name", company_name)] + en_lines),
    }


def build_company_embedding_texts(row: dict[str, Any], active_cols: list[str] | None = None) -> dict[str, str]:
    """Build Italian and English embedding texts for a company."""
    if active_cols:
        return build_company_embedding_texts_dynamic(row, active_cols)
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


def _company_document_from_row(
    row: dict[str, Any],
    embedding_service: EmbeddingService,
    active_cols: list[str] | None = None,
) -> dict[str, Any] | None:
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
    embedding_texts = build_company_embedding_texts(row, active_cols)
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
    return document


def _load_active_columns(control_path: str | None) -> list[str]:
    """Load columns marked with 1 in Sheet2 (or fallback to first available sheet) of the control file."""
    import os
    if not control_path or not os.path.exists(control_path):
        return []
    try:
        logger.info("Loading active embedding columns from: %s", control_path)
        xl = pd.ExcelFile(control_path)
        sheet_name = "Sheet2" if "Sheet2" in xl.sheet_names else xl.sheet_names[0]
        df = pd.read_excel(control_path, sheet_name=sheet_name, dtype=object)
        if df.empty:
            return []
        row0 = df.iloc[0]
        active_cols = []
        for col, val in row0.items():
            try:
                if int(float(val)) == 1:
                    active_cols.append(col)
            except (ValueError, TypeError):
                pass
        logger.info("Active embedding columns: %s", active_cols)
        return active_cols
    except Exception as e:
        logger.error("Failed loading active columns from control file: %s", e)
        return []


def build_company_documents(
    path: str,
    embedding_service: EmbeddingService,
    sheet_name: str = "Results",
    limit: int | None = None,
    control_path: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Read the company Excel file and return validated MongoDB documents."""
    import os
    from pathlib import Path
    
    # Auto-detect control file if not explicitly passed
    if not control_path:
        for file in Path(path).parent.iterdir():
            if file.is_file() and file.suffix.lower() in {".xlsx", ".xlsm", ".xls"}:
                name_lower = file.name.lower()
                if "control" in name_lower or "controllo" in name_lower or "embedding" in name_lower:
                    control_path = str(file)
                    break
                    
    active_cols = _load_active_columns(control_path)
    
    # Build custom aliases to map dynamic active columns
    custom_aliases = COMPANY_COLUMN_ALIASES.copy()
    if active_cols:
        for col in active_cols:
            normalized_col = normalize_column_name(col)
            already_mapped = False
            for field, aliases_list in custom_aliases.items():
                if any(normalize_column_name(a) == normalized_col for a in aliases_list):
                    already_mapped = True
                    break
            if not already_mapped:
                field_name = f"custom_{normalized_col}"
                custom_aliases[field_name] = [col]
                
    frame = pd.read_excel(path, sheet_name=sheet_name, dtype=object)
    if limit:
        frame = frame.head(limit)
    rows = rename_columns(frame.to_dict(orient="records"), custom_aliases)
    raw_documents: list[dict[str, Any]] = []
    errors = 0
    for row in rows:
        document = _company_document_from_row(row, embedding_service, active_cols=active_cols)
        if document is None:
            errors += 1
            continue
        raw_documents.append(document)

    # Batch embedding generation
    if embedding_service.enabled and raw_documents:
        it_texts = [doc["embeddings"]["it"]["text"] for doc in raw_documents]
        en_texts = [doc["embeddings"]["en"]["text"] for doc in raw_documents]
        
        logger.info("Generating embeddings in batches of 500 for %d companies...", len(raw_documents))
        
        it_vectors = []
        en_vectors = []
        batch_size = 500
        
        # Embed Italian texts
        for i in range(0, len(it_texts), batch_size):
            batch = it_texts[i:i+batch_size]
            logger.info("Embedding Italian batch %d/%d...", (i//batch_size)+1, (len(it_texts)-1)//batch_size + 1)
            it_vectors.extend(embedding_service.embed_documents(batch))
            
        # Embed English texts
        for i in range(0, len(en_texts), batch_size):
            batch = en_texts[i:i+batch_size]
            logger.info("Embedding English batch %d/%d...", (i//batch_size)+1, (len(en_texts)-1)//batch_size + 1)
            en_vectors.extend(embedding_service.embed_documents(batch))
            
        # Assign vectors back to documents
        for doc, it_vec, en_vec in zip(raw_documents, it_vectors, en_vectors):
            doc["embeddings"]["it"]["vector"] = it_vec
            doc["embeddings"]["it"]["model"] = embedding_service.settings.embedding_model if it_vec else None
            doc["embeddings"]["en"]["vector"] = en_vec
            doc["embeddings"]["en"]["model"] = embedding_service.settings.embedding_model if en_vec else None

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
