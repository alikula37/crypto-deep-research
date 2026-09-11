"""RAG motoru: haber, analiz ve raporlari indeksler; hibrit arama yapar."""

from __future__ import annotations

import logging
from datetime import datetime

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
        results: list[RetrievedContext] = []
        vector = self.embedder.embed_one(query)
        if vector:
            rows = self.store.search(vector, k=k, coin=coin)
            for row in rows:
                results.append(
                    RetrievedContext(
                        key=row.get("id", ""),
                        content=row.get("text", "")[:1200],
                        score=float(row.get("score", 0.0)),
                        source=row.get("source"),
                        coin=row.get("coin"),
                        kind=row.get("kind"),
                        timestamp=datetime.fromtimestamp(row["ts"]) if row.get("ts") else None,
                    )
                )
        if not results:
            rows = self.db.search_documents(query, coin=coin, limit=k)
            for row in rows:
                rank = row.get("rank")
                score = 1.0 / (1.0 + abs(float(rank))) if rank is not None else 0.3
                results.append(
                    RetrievedContext(
                        key=row.get("id", ""),
                        content=(row.get("text") or "")[:1200],
                        score=score,
                        source=row.get("source"),
                        coin=row.get("coin"),
                        kind=row.get("kind"),
                        timestamp=datetime.fromtimestamp(row["ts"]) if row.get("ts") else None,
                    )
                )
        return results

    def build_context(self, query: str, coin: str | None = None, k: int = 8) -> str:
        results = self.search(query, coin=coin, k=k)
        if not results:
            return "Ilgili kaynak bulunamadi."
        lines = [f"Soru: {query}", ""]
        for index, item in enumerate(results, 1):
            when = item.timestamp.strftime("%Y-%m-%d %H:%M") if item.timestamp else "tarih yok"
            lines.append(f"[{index}] ({item.source or 'kaynak'}, {when}) {item.content[:500]}")
        return "\n".join(lines)

    def answer_prompt(self, query: str, coin: str | None = None) -> str:
        """Harici LLM'e verilecek RAG prompt'u uretir."""
        context = self.build_context(query, coin=coin)
        return (
            "Asagidaki kaynaklara dayanarak soruyu Turkce, kaynak numaralarina atif yaparak yanitla.\n"
            "Bilgi yoksa bunu acikca belirt, uydurma.\n\n"
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
