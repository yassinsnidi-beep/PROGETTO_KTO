"""Ingest UNIBO alumni Excel files into MongoDB-ready documents."""

from __future__ import annotations

import difflib
import logging
import re
import sys
from typing import Any
import pandas as pd
from pydantic import ValidationError

from src.db import get_database, ensure_indexes, upsert_documents
from src.models import AlumnusDocument
from src.utils import clean_string, utc_now_iso
from src.ingestion.normalization import normalized_name

logger = logging.getLogger(__name__)


def clean_company_name(name: Any) -> str | None:
    """Clean and strip corporate suffixes from company name for robust matching."""
    norm = normalized_name(name)
    if not norm:
        return None
    # Remove spaces inside corporate forms: e.g. "s r l" -> "srl", "s p a" -> "spa"
    norm = re.sub(r"\b(s\s*r\s*l|s\s*p\s*a|s\s*n\s*c|s\s*a\s*s)\b", lambda m: m.group(0).replace(" ", ""), norm)
    # Remove common corporate suffixes
    suffixes = r'\b(srl|spa|srls|sas|snc|coop|ltd|inc|co|gmbh)\b'
    norm = re.sub(suffixes, "", norm)
    return re.sub(r"\s+", " ", norm).strip() or None


def build_alumnus_document(row: dict[str, Any], company_map: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    alumnus_id = row.get("ID")
    if pd.isna(alumnus_id) or alumnus_id is None:
        logger.error("Skipping alumnus without ID: %r", row)
        return None
        
    now = utc_now_iso()
    
    # Build list of degrees (up to 3)
    degrees = []
    for i in range(1, 4):
        deg_type = clean_string(row.get(f"Studio {i} - Tipo"))
        if deg_type:
            degrees.append({
                "type": deg_type,
                "course": clean_string(row.get(f"Studio {i} - Corso")),
                "department": clean_string(row.get(f"Studio {i} - Dipartimento")),
                "year": clean_string(row.get(f"Studio {i} - Anno")),
                "city": clean_string(row.get(f"Studio {i} - Sede")),
            })
            
    # Build list of jobs (up to 3)
    jobs = []
    for i in range(1, 4):
        job_company = clean_string(row.get(f"Lavoro {i} - Azienda"))
        if job_company:
            jobs.append({
                "company": job_company,
                "role": clean_string(row.get(f"Lavoro {i} - Ruolo")),
            })
            
    # Association logic with AIDA companies (using Lavoro 1 - Azienda)
    company_raw = clean_string(row.get("Lavoro 1 - Azienda"))
    company_id = None
    company_name_matched = None
    
    if company_raw:
        clean_alumni_co = clean_company_name(company_raw)
        if clean_alumni_co:
            # Try exact match
            match = company_map.get(clean_alumni_co)
            if match:
                company_id = match["id"]
                company_name_matched = match["original_name"]
            else:
                # Try fast prefix/suffix match
                for db_clean_name in company_map:
                    if len(clean_alumni_co) > 3 and (db_clean_name.startswith(clean_alumni_co) or clean_alumni_co.startswith(db_clean_name)):
                        match = company_map[db_clean_name]
                        company_id = match["id"]
                        company_name_matched = match["original_name"]
                        break
                    
    document = {
        "_id": int(alumnus_id),
        "first_name": clean_string(row.get("Nome")),
        "last_name": clean_string(row.get("Cognome")),
        "email": clean_string(row.get("Email")),
        "willing_to_help": str(row.get("Willing to Help")).strip().lower() == "sì",
        "photo_url": clean_string(row.get("Foto URL")),
        "status": int(row["Stato"]) if not pd.isna(row.get("Stato")) else None,
        "badges": clean_string(row.get("Badges")),
        "degrees": degrees,
        "jobs": jobs,
        "company_id": company_id,
        "company_name_matched": company_name_matched,
        "company_raw": company_raw,
        "created_at": now,
        "updated_at": now,
    }
    return document


def main():
    print("=" * 60)
    print("        ALUMNI INGESTION PIPELINE")
    print("=" * 60)
    
    db = get_database()
    print("[1] Caricamento aziende da MongoDB in corso...")
    db_companies = list(db.companies.find({}, {"_id": 1, "company_name": 1}))
    
    company_map = {}
    for c in db_companies:
        clean_db_name = clean_company_name(c.get("company_name"))
        if clean_db_name:
            company_map[clean_db_name] = {
                "id": c["_id"],
                "original_name": c["company_name"]
            }
    print(f"[+] Caricate {len(company_map)} aziende uniche per il matching.")
    
    excel_path = "alumni_unibo.xlsx"
    print(f"[2] Caricamento del file Excel: {excel_path}...")
    try:
        frame = pd.read_excel(excel_path, dtype=object)
    except Exception as e:
        print(f"[-] Errore nel caricamento del file Excel: {e}")
        sys.exit(1)
        
    print(f"[+] Caricate {len(frame)} righe da Excel.")
    
    print("[3] Esecuzione del matching e validazione dei documenti...")
    documents = []
    errors = 0
    matches_count = 0
    
    rows = frame.to_dict(orient="records")
    for row in rows:
        document = build_alumnus_document(row, company_map)
        if document is None:
            errors += 1
            continue
        try:
            model = AlumnusDocument.model_validate(document)
            doc_dict = model.model_dump(by_alias=True)
            documents.append(doc_dict)
            if doc_dict.get("company_id"):
                matches_count += 1
        except ValidationError as e:
            errors += 1
            logger.exception("Invalid alumnus document skipped: %s", document.get("_id"))
            
    print(f"[+] Match completati con successo per {matches_count} alumni su {len(documents)} validi.")
    if errors > 0:
        print(f"[!] Saltati {errors} documenti non validi.")
        
    if documents:
        print(f"[4] Salvataggio dei documenti su MongoDB (collezione 'alumni')...")
        ensure_indexes(db)
        upserted = upsert_documents("alumni", documents, db=db)
        print(f"[+] Successo! {upserted} documenti caricati/aggiornati in MongoDB.")
    else:
        print("[-] Nessun documento valido da caricare.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
