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
from crypto_deep_research.rag.chunking import reconstruct_chunk_text, split_text, whitespace_offsets
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
            current = contexts.get(item.key)
            if current is None:
                contexts[item.key] = item
            else:
                metadata = (
                    "source", "url", "coin", "kind", "parent_id", "chunk_index",
                    "token_start", "token_count", "timestamp",
                )
                contexts[item.key] = current.model_copy(
                    update={
                        field: getattr(item, field)
                        for field in metadata
                        if getattr(current, field) in (None, 0) and getattr(item, field) not in (None, 0)
                    }
                )
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

    def _ingest_rows(
        self,
        rows: list[dict],
        *,
        chunk_tokens: int | None = None,
        overlap_tokens: int | None = None,
    ) -> int:
        chunk_size = self.settings.rag_chunk_tokens if chunk_tokens is None else chunk_tokens
        overlap_size = (
            self.settings.rag_chunk_overlap_tokens if overlap_tokens is None else overlap_tokens
        )
        if chunk_size < 1 or overlap_size < 0 or overlap_size >= chunk_size:
            raise ValueError("chunk_tokens pozitif, overlap_tokens ise 0 <= overlap < chunk olmalı")
        chunked_rows: list[dict] = []
        for row in rows:
            parent_id = row["id"]
            offsets = self.embedder.token_offsets(row["text"])
            chunks = split_text(
                row["text"],
                offsets if offsets is not None else whitespace_offsets(row["text"]),
                chunk_tokens=chunk_size,
                overlap_tokens=overlap_size,
            )
            self.db.delete_documents(parent_id)
            self.store.delete_document(parent_id)
            self.db.save_rag_source_document(
                parent_id,
                row["coin"],
                row["kind"],
                row["source"],
                row["url"],
                row["text"],
                row["ts"],
            )
            for index, chunk in enumerate(chunks):
                chunk_id = (
                    parent_id if len(chunks) == 1 else f"{parent_id}#chunk-{index:06d}"
                )
                self.db.save_document(
                    chunk_id,
                    row["coin"],
                    row["kind"],
                    row["source"],
                    row["url"],
                    chunk.text,
                    row["ts"],
                    parent_id=parent_id,
                    chunk_index=index,
                    token_start=chunk.token_start,
                    token_count=chunk.token_count,
                )
                chunked_rows.append({**row, "id": chunk_id, "text": chunk.text})

        self._embed_and_store(chunked_rows)
        return len(chunked_rows)

    def reindex(
        self, *, chunk_tokens: int | None = None, overlap_tokens: int | None = None
    ) -> dict[str, int]:
        """Rebuild the index from complete sources, recovering legacy chunk groups once."""
        archived = {row["id"]: row for row in self.db.list_rag_source_documents()}
        legacy_groups: dict[str, list[dict]] = {}
        for row in self.db.list_documents():
            parent_id = row.get("parent_id") or row["id"]
            if parent_id not in archived:
                legacy_groups.setdefault(parent_id, []).append(row)

        recovered = 0
        for parent_id, chunks in legacy_groups.items():
            first = min(chunks, key=lambda item: (item["chunk_index"], item["id"]))
            archived[parent_id] = {
                "id": parent_id,
                "coin": first.get("coin"),
                "kind": first.get("kind") or "document",
                "source": first.get("source"),
                "url": first.get("url"),
                "text": reconstruct_chunk_text(chunks),
                "ts": first.get("ts"),
            }
            recovered += 1

        rows = list(archived.values())
        chunk_count = self._ingest_rows(
            rows,
            chunk_tokens=chunk_tokens,
            overlap_tokens=overlap_tokens,
        )
        return {
            "source_documents": len(rows),
            "legacy_documents_recovered": recovered,
            "chunks_indexed": chunk_count,
        }

    def ingest_articles(self, coin_id: str, articles: list[NewsArticle]) -> int:
        rows: list[dict] = []
        for article in articles:
            text = article.text_for_embedding()
            doc_id = make_doc_id("news", article.url or article.title)
            ts = article.published_at.timestamp() if article.published_at else now_ts()
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
        return self._ingest_rows(rows)

    def ingest_analysis(self, coin_id: str, results: list[AnalysisResult]) -> int:
        rows: list[dict] = []
        for result in results:
            text = f"## {result.title}\n{result.summary}\nDurum: {result.status}\nSkor: {result.score}"
            if result.data.get("reasons"):
                text += "\nNedenler: " + "; ".join(str(r) for r in result.data["reasons"][:8])
            doc_id = make_doc_id("analysis", f"{coin_id}:{result.key}")
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
        return self._ingest_rows(rows)

    def ingest_report(self, coin_id: str, name: str, markdown: str) -> int:
        doc_id = make_doc_id("report", name)
        return self._ingest_rows(
            [
                {
                    "id": doc_id,
                    "coin": coin_id,
                    "kind": "report",
                    "source": "report",
                    "url": None,
                    "text": markdown,
                    "ts": now_ts(),
                }
            ]
        )

    # ------------------------------------------------------------------ arama
    def search(
        self,
        query: str,
        coin: str | None = None,
        k: int = 8,
        *,
        mode: str = "hybrid",
    ) -> list[RetrievedContext]:
        if mode not in {"dense", "bm25", "hybrid"}:
            raise ValueError("mode 'dense', 'bm25' veya 'hybrid' olmalı")
        k = max(1, int(k))
        candidate_count = max(k * RERANK_CANDIDATE_MULTIPLIER, MIN_RERANK_CANDIDATES)
        vector_results: list[RetrievedContext] = []
        if mode != "bm25":
            vector = self.embedder.embed_one(query)
        else:
            vector = None
        if vector:
            rows = self.store.search(vector, k=candidate_count, coin=coin)
            for row in rows:
                vector_results.append(
                    RetrievedContext(
                        key=row.get("id", ""),
                        content=row.get("text", ""),
                        score=float(row.get("score", 0.0)),
                        score_type="dense",
                        source=row.get("source"),
                        url=row.get("url"),
                        coin=row.get("coin"),
                        kind=row.get("kind"),
                        parent_id=row.get("id", "").partition("#chunk-")[0],
                        chunk_index=int(row.get("id", "").rsplit("#chunk-", 1)[-1])
                        if "#chunk-" in row.get("id", "")
                        else 0,
                        timestamp=datetime.fromtimestamp(row["ts"]) if row.get("ts") else None,
                    )
                )
        lexical_rows = (
            self.db.search_documents(query, coin=coin, limit=candidate_count)
            if mode != "dense"
            else []
        )
        lexical_results = [
            RetrievedContext(
                key=row.get("id", ""),
                content=row.get("text") or "",
                score=0.0,
                score_type="bm25",
                source=row.get("source"),
                url=row.get("url"),
                coin=row.get("coin"),
                kind=row.get("kind"),
                parent_id=row.get("parent_id"),
                chunk_index=int(row.get("chunk_index") or 0),
                token_start=int(row.get("token_start") or 0),
                token_count=int(row.get("token_count") or 0),
                timestamp=datetime.fromtimestamp(row["ts"]) if row.get("ts") else None,
            )
            for row in lexical_rows
        ]
        if mode == "dense":
            results = vector_results[:candidate_count]
        elif mode == "bm25":
            results = lexical_results[:candidate_count]
        else:
            results = reciprocal_rank_fusion(
                [vector_results, lexical_results], limit=candidate_count
            )
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

    def _format_context(self, query: str, results: list[RetrievedContext]) -> str:
        if not results:
            return "Ilgili kaynak bulunamadı."
        lines = [f"Soru: {query}", ""]
        for index, item in enumerate(results, 1):
            when = item.timestamp.strftime("%Y-%m-%d %H:%M") if item.timestamp else "tarih yok"
            url = f", {item.url}" if item.url else ""
            lines.append(f"[{index}] ({item.source or 'kaynak'}, {when}{url}) {item.content}")
        return "\n".join(lines)

    def build_context(self, query: str, coin: str | None = None, k: int = 8) -> str:
        return self._format_context(query, self.search(query, coin=coin, k=k))

    def answer_prompt(
        self,
        query: str,
        coin: str | None = None,
        *,
        results: list[RetrievedContext] | None = None,
    ) -> str:
        """Harici LLM'e verilecek RAG prompt'u üretir."""
        contexts = results if results is not None else self.search(query, coin=coin)
        context = self._format_context(query, contexts)
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
