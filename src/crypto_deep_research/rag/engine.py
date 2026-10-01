"""RAG motoru: haber, analiz ve raporlari indeksler; hibrit arama yapar."""

from __future__ import annotations

import logging
import threading
from datetime import datetime
from typing import Any

from crypto_deep_research.config import Settings
from crypto_deep_research.models import (
    AnalysisResult,
    NewsArticle,
    RetrievedContext,
    utcnow,
)
from crypto_deep_research.rag.embeddings import Embedder
from crypto_deep_research.rag.store import VectorStore, make_doc_id, now_ts
from crypto_deep_research.storage.db import Database

logger = logging.getLogger(__name__)
RRF_RANK_CONSTANT = 60
RERANK_CANDIDATE_MULTIPLIER = 4
MIN_RERANK_CANDIDATES = 32
_RERANKER_LOCK = threading.Lock()
_RERANKERS: dict[str, Any | None] = {}


def reciprocal_rank_fusion(
    rankings: list[list[RetrievedContext]], *, limit: int, rank_constant: int = RRF_RANK_CONSTANT
) -> list[RetrievedContext]:
    """Merge independently ranked retrieval lists using reciprocal-rank fusion."""
    scores: dict[str, float] = {}
    contexts: dict[str, RetrievedContext] = {}
    for ranking in rankings:
        seen: set[str] = set()
        rank = 0
        for item in ranking:
            if item.key in seen:
                continue
            seen.add(item.key)
            rank += 1
            scores[item.key] = scores.get(item.key, 0.0) + 1.0 / (rank_constant + rank)
            contexts.setdefault(item.key, item)
    ordered = sorted(scores, key=lambda key: (-scores[key], key))[:limit]
    return [
        contexts[key].model_copy(update={"score": scores[key], "score_type": "rrf"})
        for key in ordered
    ]


def _get_reranker(model_name: str | None) -> Any | None:
    """Load one local FastEmbed cross-encoder per process, on first use."""
    if not model_name:
        return None
    if model_name in _RERANKERS:
        return _RERANKERS[model_name]
    with _RERANKER_LOCK:
        if model_name in _RERANKERS:
            return _RERANKERS[model_name]
        try:
            from fastembed.rerank.cross_encoder import TextCrossEncoder

            _RERANKERS[model_name] = TextCrossEncoder(model_name=model_name)
        except Exception as exc:
            logger.warning("RAG reranker yüklenemedi (%s): %s", model_name, exc)
            _RERANKERS[model_name] = None
    return _RERANKERS[model_name]


class RAGEngine:
    def __init__(self, db: Database, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self.embedder = Embedder(settings.embedding_model, settings.embeddings_enabled)
        self.store = VectorStore(settings.vector_dir)

    # ------------------------------------------------------------------ indeksleme
    def _embed_and_store(self, rows: list[dict]) -> None:
        if not rows:
            return
        texts = [row["text"] for row in rows]
        vectors = self.embedder.embed(texts)
        if not vectors:
            return
        for row, vector in zip(rows, vectors, strict=False):
            row["vector"] = vector
        self.store.add(rows)

    def ingest_articles(self, coin_id: str, articles: list[NewsArticle]) -> int:
        rows: list[dict] = []
        for article in articles:
            text = article.text_for_embedding()
            doc_id = make_doc_id("news", article.url or article.title)
            ts = article.published_at.timestamp() if article.published_at else now_ts()
            self.db.save_document(
                doc_id, coin_id, "news", article.source, article.url, text, ts
            )
            rows.append(
                {
                    "id": doc_id,
                    "coin": coin_id,
                    "kind": "news",
                    "source": article.source,
                    "url": article.url,
                    "text": text,
                    "ts": ts,
                }
            )
        self._embed_and_store(rows)
        return len(rows)

    def ingest_analysis(self, coin_id: str, results: list[AnalysisResult]) -> int:
        rows: list[dict] = []
        for result in results:
            text = f"## {result.title}\n{result.summary}\nDurum: {result.status}\nSkor: {result.score}"
            if result.data.get("reasons"):
                text += "\nNedenler: " + "; ".join(str(r) for r in result.data["reasons"][:8])
            doc_id = make_doc_id("analysis", f"{coin_id}:{result.key}")
            self.db.save_document(doc_id, coin_id, "analysis", "pipeline", None, text, now_ts())
            rows.append(
                {
                    "id": doc_id,
                    "coin": coin_id,
                    "kind": "analysis",
                    "source": "pipeline",
                    "url": None,
                    "text": text,
                    "ts": now_ts(),
                }
            )
        self._embed_and_store(rows)
        return len(rows)

    def ingest_report(self, coin_id: str, name: str, markdown: str) -> int:
        doc_id = make_doc_id("report", name)
        self.db.save_document(doc_id, coin_id, "report", "report", None, markdown[:20000], now_ts())
        self._embed_and_store(
            [
                {
                    "id": doc_id,
                    "coin": coin_id,
                    "kind": "report",
                    "source": "report",
                    "url": None,
                    "text": markdown[:8000],
                    "ts": now_ts(),
                }
            ]
        )
        return 1

    # ------------------------------------------------------------------ arama
    def search(self, query: str, coin: str | None = None, k: int = 8) -> list[RetrievedContext]:
        k = max(1, int(k))
        candidate_count = max(k * RERANK_CANDIDATE_MULTIPLIER, MIN_RERANK_CANDIDATES)
        vector_results: list[RetrievedContext] = []
        vector = self.embedder.embed_one(query)
        if vector:
            rows = self.store.search(vector, k=candidate_count, coin=coin)
            for row in rows:
                vector_results.append(
                    RetrievedContext(
                        key=row.get("id", ""),
                        content=row.get("text", "")[:1200],
                        score=float(row.get("score", 0.0)),
                        source=row.get("source"),
                        url=row.get("url"),
                        coin=row.get("coin"),
                        kind=row.get("kind"),
                        timestamp=datetime.fromtimestamp(row["ts"]) if row.get("ts") else None,
                    )
                )
        lexical_results = [
            RetrievedContext(
                key=row.get("id", ""),
                content=(row.get("text") or "")[:1200],
                score=0.0,
                source=row.get("source"),
                url=row.get("url"),
                coin=row.get("coin"),
                kind=row.get("kind"),
                timestamp=datetime.fromtimestamp(row["ts"]) if row.get("ts") else None,
            )
            for row in self.db.search_documents(query, coin=coin, limit=candidate_count)
        ]
        results = reciprocal_rank_fusion([vector_results, lexical_results], limit=candidate_count)
        if not results:
            return []

        reranker = _get_reranker(self.settings.rag_reranker_model)
        if reranker is None:
            return results[:k]
        try:
            scores = list(reranker.rerank(query, [item.content for item in results]))
            if len(scores) != len(results):
                raise ValueError("Reranker sonucu aday sayısıyla eşleşmiyor")
            reranked = [
                item.model_copy(update={"score": float(score), "score_type": "cross_encoder"})
                for item, score in zip(results, scores, strict=True)
            ]
            return sorted(reranked, key=lambda item: item.score, reverse=True)[:k]
        except Exception as exc:
            logger.warning("RAG reranking başarısız, RRF sıralaması kullanılıyor: %s", exc)
            return results[:k]

    def build_context(self, query: str, coin: str | None = None, k: int = 8) -> str:
        results = self.search(query, coin=coin, k=k)
        if not results:
            return "Ilgili kaynak bulunamadı."
        lines = [f"Soru: {query}", ""]
        for index, item in enumerate(results, 1):
            when = item.timestamp.strftime("%Y-%m-%d %H:%M") if item.timestamp else "tarih yok"
            url = f", {item.url}" if item.url else ""
            lines.append(f"[{index}] ({item.source or 'kaynak'}, {when}{url}) {item.content[:500]}")
        return "\n".join(lines)

    def answer_prompt(self, query: str, coin: str | None = None) -> str:
        """Harici LLM'e verilecek RAG prompt'u üretir."""
        context = self.build_context(query, coin=coin)
        return (
            "Aşağıdaki kaynaklara dayanarak soruyu Turkce, kaynak numaralarina atif yaparak yanitla.\n"
            "Bilgi yoksa bunu açıkça belirt, uydurma.\n\n"
            f"{context}\n\nSorunun cevabi:"
        )

    def stats(self) -> dict:
        return {
            "documents": self.db.document_count(),
            "vectors": self.store.count(),
            "embedder": {
                "model": self.embedder.model_name,
                "available": self.embedder.available,
                "enabled": self.embedder.enabled,
            },
            "vector_store_available": self.store.available,
            "checked_at": utcnow().isoformat(),
        }
