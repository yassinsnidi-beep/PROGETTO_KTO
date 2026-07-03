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
    return MongoClient(settings.mongodb_uri, tlsCAFile=certifi.where())


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
    """Upsert documents by _id using bulk ReplaceOne operations."""
    if not documents:
        return 0
    if db is None:
        db = get_database(settings)
    operations = [
        ReplaceOne({"_id": document["_id"]}, document, upsert=True)
        for document in documents
        if document.get("_id")
    ]
    if not operations:
        return 0
    result = db[collection_name].bulk_write(operations, ordered=False)
    upserted = len(result.upserted_ids)
    modified = result.modified_count
    matched_without_change = max(result.matched_count - modified, 0)
    count = upserted + modified + matched_without_change
    logger.info("Upserted %s documents into %s", count, collection_name)
    return count
