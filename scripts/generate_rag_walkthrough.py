"""Regenerate teaching fixtures with cached tokenizer and isolated real retrieval.

Run: uv run python scripts/generate_rag_walkthrough.py
The fictional source text lives in the JSON fixture. Both chunking strategies
use the actual backend; no production database, settings or OpenRouter is used.
Reranking and answers remain authored illustrations, not model measurements.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from fastembed.common.utils import define_cache_dir
from tokenizers import Tokenizer

from crypto_deep_research.models import RetrievedContext
from crypto_deep_research.rag.chunking import TextChunk, sentence_token_spans, split_text
from crypto_deep_research.rag.embeddings import Embedder
from crypto_deep_research.rag.engine import reciprocal_rank_fusion
from crypto_deep_research.rag.store import VectorStore
from crypto_deep_research.storage.db import Database

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "web/src/fixtures/rag-demo-tokens.json"
MODEL = "intfloat/multilingual-e5-large"
QUERY = "Bitcoin’de fonlama yükselirken likidasyon riskini nasıl yorumlamalıyım?"
FUNDING_QUOTE = "Fonlamanın yüksek olması tek başına fiyatın düşeceğini kanıtlamaz."
RISK_QUOTE = "Likidasyon riski; kaldıraç oranına, teminata ve pozisyon büyüklüğüne bağlıdır."


def measure_retrieval(chunks: list[TextChunk], embedder: Embedder, fixture: dict, strategy: str) -> dict:
    vectors = embedder.embed([QUERY, *(chunk.text for chunk in chunks)])
    if not vectors or embedder.model_name != MODEL:
        raise RuntimeError("Cached embedding modeli kullanılamadı; sahte embedding kaydedilmedi.")
    query_vector, *chunk_vectors = [[float(value) for value in vector] for vector in vectors]
    documents = [
        {
            "id": f"C{index + 1}",
            "title": f"Pasaj {index + 1} · {chunk.text[:60]}",
            "excerpt": chunk.text,
            "source": fixture["source"],
            "parentId": fixture["id"],
            "tokenStart": chunk.token_start,
            "tokenCount": chunk.token_count,
            "vectorPreview": vector[:8],
            "vectorDimension": len(vector),
        }
        for index, (chunk, vector) in enumerate(zip(chunks, chunk_vectors, strict=True))
    ]
    with tempfile.TemporaryDirectory(prefix="cdr-rag-walkthrough-") as directory:
        scratch = Path(directory)
        db = Database(scratch / "demo.sqlite")
        store = VectorStore(scratch / "vectors")
        if not store.available:
            raise RuntimeError("Geçici LanceDB kullanılamadı; dense sonucu uydurulmadı.")
        rows = []
        for index, (doc, vector) in enumerate(zip(documents, chunk_vectors, strict=True)):
            db.save_document(
                doc["id"], "bitcoin", "demo", fixture["source"], None, doc["excerpt"],
                parent_id=fixture["id"], chunk_index=index,
                token_start=doc["tokenStart"], token_count=doc["tokenCount"],
            )
            rows.append({
                "id": doc["id"], "coin": "bitcoin", "kind": "demo",
                "source": fixture["source"], "url": "", "text": doc["excerpt"],
                "ts": 0.0, "vector": vector,
            })
        if not store.add(rows):
            raise RuntimeError("Geçici LanceDB yazılamadı.")
        dense_rows = store.search(query_vector, k=len(documents), coin="bitcoin")
        bm25_rows = db.search_documents(QUERY, coin="bitcoin", limit=len(documents))
        db.close()
    dense = [row["id"] for row in dense_rows]
    bm25 = [row["id"] for row in bm25_rows]
    rankings = [
        [RetrievedContext(key=key, content="", score=0.0) for key in ids]
        for ids in (dense, bm25)
    ]
    fused = reciprocal_rank_fusion(rankings, limit=len(documents))
    dense_scores = {row["id"]: float(row["score"]) for row in dense_rows}
    bm25_scores = {row["id"]: float(row["rank"]) for row in bm25_rows}
    for doc in documents:
        doc["denseScore"] = dense_scores.get(doc["id"])
        doc["bm25Score"] = bm25_scores.get(doc["id"])
    # Authored reorder to illustrate citation-index changes, never a reranker run.
    priority = [
        next(doc["id"] for doc in documents if quote in doc["excerpt"])
        for quote in (RISK_QUOTE, FUNDING_QUOTE)
    ]
    reranked = list(dict.fromkeys([*priority, *dense]))
    if strategy == "token":
        reranked = ["C2", "C1", "C3", "C5", "C4"]
    return {
        "query": QUERY, "documents": documents, "dense": dense, "bm25": bm25,
        "fused": [{"id": item.key, "score": item.score} for item in fused],
        "reranked": reranked, "queryVectorPreview": query_vector[:8],
        "vectorDimension": len(query_vector),
        "provenance": {
            "computedAt": datetime.now(timezone.utc).isoformat(),
            "model": embedder.model_name, "sourceIsFictional": True,
            "denseIsMeasured": True, "bm25IsMeasured": True, "rrfIsComputed": True,
            "rerankerIsIllustrative": True, "answerIsIllustrative": True,
            "chunkTokens": 240, "overlapTokens": 40, "chunkStrategy": strategy,
            "rankConstant": 60, "candidateCount": len(documents),
            "actualOverlaps": [
                previous.token_start + previous.token_count - current.token_start
                for previous, current in zip(chunks, chunks[1:], strict=False)
            ],
            "method": "Backend split_text + Embedder + temporary VectorStore + temporary Database",
            "label": f"{strategy} / 240/40 kurgu korpusunda hesaplanan gerçek dense/BM25 sonuçları; canlı arama değildir.",
            "reproduce": "uv run python scripts/generate_rag_walkthrough.py",
        },
    }


def main() -> None:
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    fixture = json.loads(FIXTURE.read_text())
    text = fixture["text"]
    cache = Path(define_cache_dir(None))
    candidates = sorted(cache.glob("models--qdrant--multilingual-e5-large-onnx/snapshots/*/tokenizer.json"))
    if not candidates:
        raise RuntimeError("Cached multilingual-e5-large tokenizer bulunamadı; fixture değiştirilmedi.")
    tokenizer_file = candidates[-1]
    tokenizer = Tokenizer.from_file(str(tokenizer_file))
    tokenizer.no_truncation()
    tokenizer.no_padding()
    encoding = tokenizer.encode(text)
    encoded = [
        (token, int(start), int(end))
        for token, (start, end) in zip(encoding.tokens, encoding.offsets, strict=True)
        if start < end
    ]

    def utf16(offset: int) -> int:
        return len(text[:offset].encode("utf-16-le")) // 2

    fixture["tokens"] = [
        {"index": index, "start": utf16(start), "end": utf16(end),
         "text": text[start:end], "token": token}
        for index, (token, start, end) in enumerate(encoded)
    ]
    fixture["tokenCount"] = len(encoded)
    fixture["tokenizer"]["cacheRevision"] = tokenizer_file.parent.name
    offsets = [(start, end) for _, start, end in encoded]
    fixture["sentenceSpans"] = [
        {"start": start, "end": end} for start, end in sentence_token_spans(text, offsets)
    ]
    fixture["sentenceExamples"] = [
        {
            "chunkTokens": size, "overlapTokens": overlap,
            "chunks": [
                {"tokenStart": chunk.token_start, "tokenCount": chunk.token_count, "excerpt": chunk.text}
                for chunk in split_text(
                    text, offsets, chunk_tokens=size, overlap_tokens=overlap, strategy="sentence"
                )
            ],
        }
        for size, overlap in [(48, 0), (48, 8), (48, 40), (120, 20), (240, 0), (240, 40), (240, 58), (240, 80), (240, 239)]
    ]
    embedder = Embedder(MODEL)
    if embedder.token_offsets(text) != offsets:
        raise RuntimeError("Backend tokenizer tam belge offsetleriyle eşleşmedi; fixture değiştirilmedi.")
    summaries = {}
    for strategy, key in [("token", "retrieval"), ("sentence", "sentenceRetrieval")]:
        chunks = split_text(text, offsets, chunk_tokens=240, overlap_tokens=40, strategy=strategy)
        fixture[key] = measure_retrieval(chunks, embedder, fixture, strategy)
        summaries[strategy] = {
            "chunkCount": len(chunks), "actualOverlaps": fixture[key]["provenance"]["actualOverlaps"],
            "dense": fixture[key]["dense"], "bm25": fixture[key]["bm25"],
            "rrf": [row["id"] for row in fixture[key]["fused"]],
        }
    fixture["tokenizer"]["note"] = "Tam belge tokenizer offsetleri; token ve sentence stratejileri ayrı 240/40 korpuslarında ölçüldü."
    FIXTURE.write_text(json.dumps(fixture, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"tokens": len(encoded), "vectorDimension": fixture["retrieval"]["vectorDimension"], **summaries}, ensure_ascii=False))


if __name__ == "__main__":
    main()
