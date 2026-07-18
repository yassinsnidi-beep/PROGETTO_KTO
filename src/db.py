"""MongoDB helpers for indexes and upserts."""

from __future__ import annotations

import logging
from typing import Any

import certifi
from pymongo import ASCENDING, TEXT, MongoClient, ReplaceOne
from pymongo.database import Database

from src.config import Settings, load_settings

logger = logging.getLogger(__name__)


def get_mongo_client(settings: Settings | None = None) -> MongoClient:
    """Create a MongoDB client from environment configuration."""
    settings = settings or load_settings()
    if not settings.mongodb_uri:
        raise ValueError("MONGODB_URI is required for MongoDB writes")
    return MongoClient(settings.mongodb_uri, tlsCAFile=certifi.where(), compressors="zlib")


def get_database(settings: Settings | None = None) -> Database:
    """Return the configured MongoDB database."""
    settings = settings or load_settings()
    client = get_mongo_client(settings)
    return client[settings.mongodb_db_name]


def ensure_indexes(db: Database) -> None:
    """Create regular MongoDB indexes used by the ingest pipeline."""
    companies = db["companies"]
    companies.create_index([("tax_code", ASCENDING)], unique=True, sparse=True)
    companies.create_index([("company_name", ASCENDING)])
    companies.create_index([("industry_classification.nace_rev_2.code", ASCENDING)])
    companies.create_index([("industry_classification.nace_rev_2.division", ASCENDING)])
    companies.create_index([("industry_classification.ateco_2007.code", ASCENDING)])
    companies.create_index([("location.province", ASCENDING)])
    companies.create_index([("metrics.technology_adoption_capacity_score", ASCENDING)])

    industries = db["industries"]
    industries.create_index([("code", ASCENDING)], unique=True)
    industries.create_index([("division.code", ASCENDING)])
    industries.create_index([("embeddings.it.text", TEXT), ("embeddings.en.text", TEXT)])

    patents = db["patents"]
    patents.create_index([("scheda_id", ASCENDING)], unique=True)
    patents.create_index(
        [
            ("title", TEXT),
            ("abstract", TEXT),
            ("full_description", TEXT),
            ("embeddings.it.text", TEXT),
            ("embeddings.en.text", TEXT),
        ]
    )


def upsert_documents(
    collection_name: str,
    documents: list[dict[str, Any]],
    db: Database | None = None,
    settings: Settings | None = None,
) -> int:
    """Upsert documents by _id using bulk ReplaceOne operations in batches of 1000."""
    if not documents:
        return 0
    if db is None:
        db = get_database(settings)

    # Check if the collection is empty. If it is, use fast insert_many!
    try:
        is_empty = db[collection_name].count_documents({}, limit=1) == 0
    except Exception:
        is_empty = False

    if is_empty:
        logger.info("Collection %s is empty. Using fast insert_many in batches of 1000...", collection_name)
        total_inserted = 0
        batch_size = 1000
        for i in range(0, len(documents), batch_size):
            batch = documents[i:i+batch_size]
            for attempt in range(3):
                try:
                    result = db[collection_name].insert_many(batch, ordered=False)
                    total_inserted += len(result.inserted_ids)
                    logger.info("Batch %d/%d completed. (Inserted %d docs so far)", (i//batch_size)+1, (len(documents)-1)//batch_size + 1, total_inserted)
                    break
                except Exception as e:
                    if attempt < 2:
                        logger.warning("Error inserting batch %d (attempt %d/3): %s. Retrying in 2 seconds...", (i//batch_size)+1, attempt+1, e)
                        import time
                        time.sleep(2)
                    else:
                        logger.error("Error inserting batch %d after all attempts: %s", (i//batch_size)+1, e)
                        raise e
        return total_inserted

    operations = [
        ReplaceOne({"_id": document["_id"]}, document, upsert=True)
        for document in documents
        if document.get("_id")
    ]
    if not operations:
        return 0
        
    batch_size = 250
    total_upserted = 0
    total_modified = 0
    total_matched = 0
    
    logger.info("Upserting %d documents into %s in batches of %d...", len(operations), collection_name, batch_size)
    for i in range(0, len(operations), batch_size):
        batch_ops = operations[i:i+batch_size]
        
        # Retry mechanism for robustness on flaky network connections (e.g. mobile hotspots)
        for attempt in range(3):
            try:
                result = db[collection_name].bulk_write(batch_ops, ordered=False)
                total_upserted += len(result.upserted_ids)
                total_modified += result.modified_count
                total_matched += result.matched_count
                logger.info("Batch %d/%d completed. (Upserted %d docs so far)", (i//batch_size)+1, (len(operations)-1)//batch_size + 1, total_upserted + total_modified)
                break
            except Exception as e:
                if attempt < 2:
                    logger.warning("Error writing batch %d (attempt %d/3): %s. Retrying in 2 seconds...", (i//batch_size)+1, attempt+1, e)
                    import time
                    time.sleep(2)
                else:
                    logger.error("Error writing batch %d after all attempts: %s", (i//batch_size)+1, e)
                    raise e
            
    matched_without_change = max(total_matched - total_modified, 0)
    count = total_upserted + total_modified + matched_without_change
    logger.info("Successfully upserted %d documents in total into %s", count, collection_name)
    return count
