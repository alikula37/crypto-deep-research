"""Yerel embedding: fastembed (ONNX) ile çok dilli vektör üretimi."""

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
    """Gec yüklenen (lazy), hata durumunda devre disi kalan embedding sarmalayicisi."""

    def __init__(self, model_name: str, enabled: bool = True) -> None:
        self.model_name = model_name
        self.enabled = enabled
        self._model: Any | None = None
        self._offset_tokenizer: Any | None = None
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
                        logger.info("Embedding modeli yüklendi: %s", candidate)
                        break
                    except Exception as exc:
                        logger.warning("Embedding modeli yüklenemedi (%s): %s", candidate, exc)
                if self._model is None:
                    self._load_failed = True
            except Exception as exc:
                logger.warning("fastembed kullanılamiyor: %s", exc)
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
            logger.warning("Embedding hatası: %s", exc)
            return None

    def embed_one(self, text: str) -> list[float] | None:
        vectors = self.embed([text])
        return vectors[0] if vectors else None

    def input_token_count(self, text: str) -> int | None:
        """Count standalone inference input, including special tokens, before truncation."""
        if self.token_offsets(text) is None or self._offset_tokenizer is None:
            return None
        with self._lock:
            return len(self._offset_tokenizer.encode(text).ids)

    @property
    def max_input_tokens(self) -> int | None:
        """Read the actual loaded model's inference tokenizer limit."""
        model = self._load()
        tokenizer = getattr(getattr(model, "model", None), "tokenizer", None)
        truncation = getattr(tokenizer, "truncation", None)
        return int(truncation["max_length"]) if truncation else None

    def token_offsets(self, text: str) -> list[tuple[int, int]] | None:
        """Return full-document offsets without changing embedding input limits."""
        model = self._load()
        if model is None:
            return None
        try:
            # _load acquires this lock itself, so load before entering it. Cache
            # a separate tokenizer: FastEmbed truncates its inference tokenizer
            # to the model limit, which would silently drop long-document tails.
            with self._lock:
                if self._offset_tokenizer is None:
                    underlying = getattr(model, "model", None)
                    tokenizer = getattr(underlying, "tokenizer", None)
                    if tokenizer is None:
                        model.token_count([text])
                        tokenizer = getattr(underlying, "tokenizer", None)
                    if tokenizer is None:
                        return None
                    from tokenizers import Tokenizer

                    offset_tokenizer = Tokenizer.from_str(tokenizer.to_str())
                    offset_tokenizer.no_truncation()
                    offset_tokenizer.no_padding()
                    self._offset_tokenizer = offset_tokenizer
                encoding = self._offset_tokenizer.encode(text)
            offsets = [(int(start), int(end)) for start, end in encoding.offsets]
            return [(start, end) for start, end in offsets if start < end]
        except Exception as exc:
            logger.warning(
                "Tokenizer offsetları alınamadı; kelime tabanlı parçalara düşülüyor: %s", exc
            )
            return None
