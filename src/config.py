"""Runtime configuration for the ingestion pipeline."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


def _as_bool(value: str | bool | None, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class Settings:
    mongodb_uri: str | None
    mongodb_db_name: str
    generate_embeddings: bool
    embedding_provider: str
    openai_api_key: str | None
    embedding_model: str
    ollama_base_url: str
    sentence_transformers_device: str | None
    gemini_api_key: str | None
    llm_model: str


def load_settings(force_generate_embeddings: bool | None = None) -> Settings:
    """Load settings from .env and environment variables."""
    load_dotenv()
    generate_embeddings = _as_bool(os.getenv("GENERATE_EMBEDDINGS"), False)
    if force_generate_embeddings is not None:
        generate_embeddings = force_generate_embeddings
    return Settings(
        mongodb_uri=os.getenv("MONGODB_URI"),
        mongodb_db_name=os.getenv("MONGODB_DB_NAME", "patent_matching"),
        generate_embeddings=generate_embeddings,
        embedding_provider=os.getenv("EMBEDDING_PROVIDER", "openai").strip().lower(),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        embedding_model=os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"),
        ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/"),
        sentence_transformers_device=os.getenv("SENTENCE_TRANSFORMERS_DEVICE") or None,
        gemini_api_key=os.getenv("GEMINI_API_KEY"),
        llm_model=os.getenv("LLM_MODEL", "gemini-1.5-flash"),
    )
