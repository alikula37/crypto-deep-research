"""Yerel embedding: fastembed (ONNX) ile cok dilli vektor uretimi."""

from __future__ import annotations

import logging
import threading
from typing import Any

logger = logging.getLogger(__name__)

FALLBACK_MODELS = [
    "intfloat/multilingual-e5-large",
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    "BAAI/bge-small-en-v1.5",
]


class Embedder:
    """Gec yuklenen (lazy), hata durumunda devre disi kalan embedding sarmalayicisi."""

    def __init__(self, model_name: str, enabled: bool = True) -> None:
        self.model_name = model_name
        self.enabled = enabled
        self._model: Any | None = None
        self._load_failed = False
        self._lock = threading.Lock()

    @property
    def available(self) -> bool:
        return self.enabled and not self._load_failed

    def _load(self) -> Any | None:
        if self._model is not None or self._load_failed or not self.enabled:
            return self._model
        with self._lock:
            if self._model is not None or self._load_failed:
                return self._model
            try:
                from fastembed import TextEmbedding

                candidates = [self.model_name] + [
                    model for model in FALLBACK_MODELS if model != self.model_name
                ]
                for candidate in candidates:
                    try:
                        self._model = TextEmbedding(model_name=candidate)
                        self.model_name = candidate
                        logger.info("Embedding modeli yuklendi: %s", candidate)
                        break
                    except Exception as exc:
                        logger.warning("Embedding modeli yuklenemedi (%s): %s", candidate, exc)
                if self._model is None:
                    self._load_failed = True
            except Exception as exc:
                logger.warning("fastembed kullanilamiyor: %s", exc)
                self._load_failed = True
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]] | None:
        if not texts:
            return []
        model = self._load()
        if model is None:
            return None
        try:
            return [list(vector) for vector in model.embed(texts)]
        except Exception as exc:
            logger.warning("Embedding hatasi: %s", exc)
            return None

    def embed_one(self, text: str) -> list[float] | None:
        vectors = self.embed([text])
        return vectors[0] if vectors else None
