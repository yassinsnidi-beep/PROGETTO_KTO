"""Optional multilingual embedding generation."""

from __future__ import annotations

import json
import logging
from typing import Any
from urllib import request

from src.config import Settings, load_settings
from src.utils import is_missing

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Generate embeddings only when enabled by configuration."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or load_settings()
        self.enabled = self.settings.generate_embeddings
        self.provider = self.settings.embedding_provider
        self._client = None
        if not self.enabled:
            return
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

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts, preserving empty slots as empty vectors."""
        if not self.enabled:
            return [[] for _ in texts]
        non_empty_positions = [idx for idx, text in enumerate(texts) if not is_missing(text)]
        non_empty_texts = [texts[idx] for idx in non_empty_positions]
        vectors: list[list[float]] = [[] for _ in texts]
        if not non_empty_texts:
            return vectors
        try:
            if self.provider == "openai":
                embedded = self._client.embed_documents(non_empty_texts)
            elif self.provider == "sentence_transformers":
                embedded = self._embed_sentence_transformers(non_empty_texts)
            elif self.provider == "ollama":
                embedded = self._embed_ollama(non_empty_texts)
            else:
                embedded = []
        except Exception:
            logger.exception("Batch embedding generation failed")
            return vectors
        for idx, vector in zip(non_empty_positions, embedded):
            vectors[idx] = list(vector)
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
