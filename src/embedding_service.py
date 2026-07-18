"""Optional multilingual embedding generation."""

from __future__ import annotations

import json
import logging
import os
from typing import Any
from urllib import request

from src.config import Settings, load_settings
from src.utils import is_missing

logger = logging.getLogger(__name__)

CACHE_PATH = r"c:\Users\Abdou\Desktop\brev_to_market\data\embeddings_cache.json"


class EmbeddingService:
    """Generate embeddings only when enabled by configuration."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or load_settings()
        self.enabled = self.settings.generate_embeddings
        self.provider = self.settings.embedding_provider
        self._client = None
        self.cache: dict[str, list[float]] = {}
        if not self.enabled:
            return
        self._load_cache()
        if self.provider == "openai":
            self._initialize_openai()
        elif self.provider == "sentence_transformers":
            self._initialize_sentence_transformers()
        elif self.provider == "ollama":
            logger.info("Using Ollama embeddings at %s", self.settings.ollama_base_url)
        else:
            logger.warning("Unsupported embedding provider: %s", self.provider)
            self.enabled = False

    def _initialize_openai(self) -> None:
        """Initialize LangChain OpenAI embeddings."""
        try:
            from langchain_openai import OpenAIEmbeddings

            self._client = OpenAIEmbeddings(
                model=self.settings.embedding_model,
                openai_api_key=self.settings.openai_api_key,
            )
        except Exception:
            logger.exception("Could not initialize OpenAI embeddings")
            self.enabled = False

    def _initialize_sentence_transformers(self) -> None:
        """Initialize a local Sentence Transformers model."""
        try:
            from sentence_transformers import SentenceTransformer

            kwargs: dict[str, Any] = {}
            if self.settings.sentence_transformers_device:
                kwargs["device"] = self.settings.sentence_transformers_device
            self._client = SentenceTransformer(self.settings.embedding_model, **kwargs)
        except Exception:
            logger.exception("Could not initialize Sentence Transformers embeddings")
            self.enabled = False

    def embed_text(self, text: str) -> list[float]:
        """Embed a single text, returning [] when disabled or empty."""
        if not self.enabled or is_missing(text):
            return []
        try:
            if self.provider == "openai":
                return list(self._client.embed_query(text))
            if self.provider == "sentence_transformers":
                return self._embed_sentence_transformers([text])[0]
            if self.provider == "ollama":
                return self._embed_ollama([text])[0]
        except Exception:
            logger.exception("Embedding generation failed for one text")
        return []

    def _load_cache(self) -> None:
        if os.path.exists(CACHE_PATH):
            try:
                with open(CACHE_PATH, "r", encoding="utf-8") as f:
                    self.cache = json.load(f)
                logger.info("Loaded %d embeddings from cache", len(self.cache))
            except Exception:
                logger.exception("Failed to load embeddings cache")
                self.cache = {}

    def _save_cache(self) -> None:
        try:
            os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
            with open(CACHE_PATH, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, ensure_ascii=False)
        except Exception:
            logger.exception("Failed to save embeddings cache")

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts, preserving empty slots as empty vectors."""
        if not self.enabled:
            return [[] for _ in texts]
            
        vectors: list[list[float]] = [[] for _ in texts]
        non_empty_positions = [idx for idx, text in enumerate(texts) if not is_missing(text)]
        
        # Check cache first
        missing_positions = []
        missing_texts = []
        
        for idx in non_empty_positions:
            text = texts[idx]
            if text in self.cache:
                vectors[idx] = self.cache[text]
            else:
                missing_positions.append(idx)
                missing_texts.append(text)
                
        if not missing_texts:
            return vectors
            
        try:
            if self.provider == "openai":
                embedded = self._client.embed_documents(missing_texts)
            elif self.provider == "sentence_transformers":
                embedded = self._embed_sentence_transformers(missing_texts)
            elif self.provider == "ollama":
                embedded = self._embed_ollama(missing_texts)
            else:
                embedded = []
        except Exception:
            logger.exception("Batch embedding generation failed")
            return vectors
            
        cache_updated = False
        for idx, vector in zip(missing_positions, embedded):
            if vector:
                vectors[idx] = list(vector)
                self.cache[texts[idx]] = list(vector)
                cache_updated = True
                
        if cache_updated:
            self._save_cache()
            
        return vectors

    def _embed_sentence_transformers(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings with a local SentenceTransformer model."""
        if self._client is None:
            return [[] for _ in texts]
        vectors = self._client.encode(
            texts,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return [vector.astype(float).tolist() for vector in vectors]

    def _embed_ollama(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings through the local Ollama HTTP API."""
        payload = json.dumps(
            {"model": self.settings.embedding_model, "input": texts},
            ensure_ascii=False,
        ).encode("utf-8")
        http_request = request.Request(
            f"{self.settings.ollama_base_url}/api/embed",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(http_request, timeout=120) as response:
            data = json.loads(response.read().decode("utf-8"))
        embeddings = data.get("embeddings")
        if isinstance(embeddings, list):
            return [list(map(float, vector)) for vector in embeddings]
        embedding = data.get("embedding")
        if isinstance(embedding, list):
            return [list(map(float, embedding))]
        logger.warning("Unexpected Ollama embedding response shape: %s", data.keys())
        return [[] for _ in texts]

    def add_embeddings_to_document(self, document: dict[str, Any]) -> dict[str, Any]:
        """Populate embeddings.it/en.vector and model for non-empty texts."""
        embeddings = document.get("embeddings") or {}
        for language in ("it", "en"):
            payload = embeddings.get(language) or {}
            text = payload.get("text", "")
            vector = self.embed_text(text)
            payload["vector"] = vector
            payload["model"] = self.settings.embedding_model if vector else None
            embeddings[language] = payload
        document["embeddings"] = embeddings
        return document
