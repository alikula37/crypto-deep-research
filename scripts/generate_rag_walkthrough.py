"""Regenerate the teaching fixture using cached tokenizer + isolated real retrieval.

Run: uv run python scripts/generate_rag_walkthrough.py
The source document is deliberately fictional. Its full text lives in the JSON
fixture, which also lets a reviewer reproduce exact character/token boundaries.
No production database, app settings, model registry, or OpenRouter is used.
Only this process may load the cached local embedding model. Reranking and the
answer remain authored teaching examples, not measured model output.
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
from crypto_deep_research.rag.chunking import split_text
from crypto_deep_research.rag.embeddings import Embedder
from crypto_deep_research.rag.engine import reciprocal_rank_fusion
from crypto_deep_research.rag.store import VectorStore
from crypto_deep_research.storage.db import Database

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "web/src/fixtures/rag-demo-tokens.json"
MODEL = "intfloat/multilingual-e5-large"
QUERY = "Bitcoin’de fonlama yükselirken likidasyon riskini nasıl yorumlamalıyım?"
TITLES = [
    "Fonlama tek başına yön kanıtı değildir",
    "Açık pozisyon, kaldıraç ve teminat",
    "Risk yorumu ve teknik görünüm",
    "Teknik sınırlar ve ETF haberleri",
    "Veri kapsamı ve yanıtın sınırları",
]


def main() -> None:
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    fixture = json.loads(FIXTURE.read_text())
    text = fixture["text"]
    cache = Path(define_cache_dir(None))
    candidates = sorted(
        cache.glob("models--qdrant--multilingual-e5-large-onnx/snapshots/*/tokenizer.json")
    )
    if not candidates:
        raise RuntimeError(
            "Cached multilingual-e5-large tokenizer bulunamadı; fixture değiştirilmedi."
        )
    tokenizer_file = candidates[-1]
    tokenizer = Tokenizer.from_file(str(tokenizer_file))
    tokenizer.no_truncation()
    encoding = tokenizer.encode(text)
    encoded = [
        (token, int(start), int(end))
        for token, (start, end) in zip(encoding.tokens, encoding.offsets, strict=True)
        if start < end
    ]

    # Python offsets count Unicode code points; browser String.slice uses UTF-16.
    def utf16(offset: int) -> int:
        return len(text[:offset].encode("utf-16-le")) // 2

    fixture["tokens"] = [
        {
            "index": index,
            "start": utf16(start),
            "end": utf16(end),
            "text": text[start:end],
            "token": token,
        }
        for index, (token, start, end) in enumerate(encoded)
    ]
    fixture["tokenCount"] = len(encoded)
    fixture["tokenizer"]["cacheRevision"] = tokenizer_file.parent.name
    offsets = [(start, end) for _, start, end in encoded]
    chunks = split_text(text, offsets, chunk_tokens=240, overlap_tokens=40)
    if len(chunks) != 5:
        raise RuntimeError(
            f"Öğretim belgesinin beş chunk üretmesi bekleniyor; bulunan: {len(chunks)}"
        )

    embedder = Embedder(MODEL)
    if embedder.token_offsets(text) != offsets:
        raise RuntimeError("Backend tokenizer tam belge offsetleriyle eşleşmedi; fixture değiştirilmedi.")
    vectors = embedder.embed([QUERY, *(chunk.text for chunk in chunks)])
    if not vectors or embedder.model_name != MODEL:
        raise RuntimeError("Cached embedding modeli kullanılamadı; sahte embedding kaydedilmedi.")
    query_vector, *chunk_vectors = [[float(value) for value in vector] for vector in vectors]
    documents = [
        {
            "id": f"C{index + 1}",
            "title": TITLES[index],
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
                doc["id"],
                "bitcoin",
                "demo",
                fixture["source"],
                None,
                doc["excerpt"],
                parent_id=fixture["id"],
                chunk_index=index,
                token_start=doc["tokenStart"],
                token_count=doc["tokenCount"],
            )
            rows.append(
                {
                    "id": doc["id"],
                    "coin": "bitcoin",
                    "kind": "demo",
                    "source": fixture["source"],
                    "url": "",
                    "text": doc["excerpt"],
                    "ts": 0.0,
                    "vector": vector,
                }
            )
        if not store.add(rows):
            raise RuntimeError("Geçici LanceDB yazılamadı.")
        dense_rows = store.search(query_vector, k=5, coin="bitcoin")
        bm25_rows = db.search_documents(QUERY, coin="bitcoin", limit=5)
        db.close()

    dense = [row["id"] for row in dense_rows]
    bm25 = [row["id"] for row in bm25_rows]
    rankings = [
        [RetrievedContext(key=key, content="", score=0.0) for key in ids] for ids in (dense, bm25)
    ]
    fused = reciprocal_rank_fusion(rankings, limit=5)
    dense_scores = {row["id"]: float(row["score"]) for row in dense_rows}
    bm25_scores = {row["id"]: float(row["rank"]) for row in bm25_rows}
    for doc in documents:
        doc["denseScore"] = dense_scores.get(doc["id"])
        doc["bm25Score"] = bm25_scores.get(doc["id"])
    fixture["retrieval"] = {
        "query": QUERY,
        "documents": documents,
        "dense": dense,
        "bm25": bm25,
        "fused": [{"id": item.key, "score": item.score} for item in fused],
        "reranked": ["C2", "C1", "C3", "C5", "C4"],
        "queryVectorPreview": query_vector[:8],
        "vectorDimension": len(query_vector),
        "provenance": {
            "computedAt": datetime.now(timezone.utc).isoformat(),
            "model": embedder.model_name,
            "sourceIsFictional": True,
            "denseIsMeasured": True,
            "bm25IsMeasured": True,
            "rrfIsComputed": True,
            "rerankerIsIllustrative": True,
            "answerIsIllustrative": True,
            "chunkTokens": 240,
            "overlapTokens": 40,
            "rankConstant": 60,
            "candidateCount": len(documents),
            "method": "Backend Embedder + temporary VectorStore + temporary Database.search_documents",
            "label": "Sabit kurgu korpusta önceden hesaplanmış gerçek dense/BM25 sonuçları; canlı arama değildir.",
            "reproduce": "uv run python scripts/generate_rag_walkthrough.py",
        },
    }
    fixture["tokenizer"]["note"] = (
        "Cached model tokenizer’ıyla tam belge kodlandı. Dense/BM25 ölçümü yalnız 240/40 demo korpusunda yapıldı."
    )
    FIXTURE.write_text(json.dumps(fixture, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                "tokens": len(encoded),
                "chunkCount": len(chunks),
                "vectorDimension": len(query_vector),
                "dense": dense,
                "bm25": bm25,
                "rrf": [item.key for item in fused],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
