from types import SimpleNamespace

import pytest

from crypto_deep_research.rag.chunking import whitespace_offsets
from crypto_deep_research.rag.engine import RAGEngine
from crypto_deep_research.storage.db import Database


class StubEmbedder:
    def __init__(self):
        self.calls = 0

    def embed_one(self, _query):
        self.calls += 1
        return [0.1, 0.2]

    def token_offsets(self, text):
        return whitespace_offsets(text)


class StubVectorStore:
    def __init__(self):
        self.calls = 0
        self.deleted = []

    def search(self, _vector, k, coin=None):
        self.calls += 1
        return [
            {"id": "dense-a", "text": "semantic result A", "score": 0.9, "coin": coin},
            {"id": "dense-b", "text": "semantic result B", "score": 0.8, "coin": coin},
        ][:k]

    def delete_document(self, doc_id):
        self.deleted.append(doc_id)


class StubDatabase:
    def __init__(self):
        self.calls = 0

    def search_documents(self, _query, coin=None, limit=8):
        self.calls += 1
        return [
            {"id": "dense-b", "parent_id": "dense-b", "text": "lexical result B", "coin": coin},
            {"id": "dense-c", "parent_id": "dense-c", "text": "lexical result C", "coin": coin},
        ][:limit]


def make_engine():
    engine = object.__new__(RAGEngine)
    engine.embedder = StubEmbedder()
    engine.store = StubVectorStore()
    engine.db = StubDatabase()
    engine.settings = SimpleNamespace(rag_reranker_model=None)
    return engine


def test_search_can_run_dense_bm25_and_hybrid_ablation_modes():
    engine = make_engine()

    dense = engine.search("query", k=3, mode="dense")
    assert [result.key for result in dense] == ["dense-a", "dense-b"]
    assert engine.store.calls == 1
    assert engine.db.calls == 0

    lexical = engine.search("query", k=3, mode="bm25")
    assert [result.key for result in lexical] == ["dense-b", "dense-c"]
    assert engine.embedder.calls == 1
    assert engine.store.calls == 1
    assert engine.db.calls == 1

    hybrid = engine.search("query", k=3, mode="hybrid")
    assert [result.key for result in hybrid] == ["dense-b", "dense-a", "dense-c"]
    assert engine.store.calls == 2
    assert engine.db.calls == 2


def test_search_rejects_unknown_retrieval_mode():
    with pytest.raises(ValueError, match="mode 'dense', 'bm25' veya 'hybrid'"):
        make_engine().search("query", mode="semantic")


def test_reindex_recovers_legacy_chunks_and_applies_new_chunk_size(tmp_path):
    db = Database(tmp_path / "rag.db")
    db.save_document(
        "legacy#chunk-000000", "bitcoin", "report", "report", None,
        "one two three four", parent_id="legacy", chunk_index=0, token_start=0, token_count=4,
    )
    db.save_document(
        "legacy#chunk-000001", "bitcoin", "report", "report", None,
        "four five six", parent_id="legacy", chunk_index=1, token_start=3, token_count=3,
    )
    engine = object.__new__(RAGEngine)
    engine.db = db
    engine.settings = SimpleNamespace(rag_chunk_tokens=240, rag_chunk_overlap_tokens=40)
    engine.embedder = StubEmbedder()
    engine.store = StubVectorStore()
    embedded_rows = []
    engine._embed_and_store = lambda rows: embedded_rows.extend(rows)

    result = engine.reindex(chunk_tokens=2, overlap_tokens=1)

    assert result == {
        "source_documents": 1,
        "legacy_documents_recovered": 1,
        "chunks_indexed": 5,
    }
    assert [row["text"] for row in embedded_rows] == [
        "one two", "two three", "three four", "four five", "five six"
    ]
    archived = db.list_rag_source_documents()
    assert len(archived) == 1
    assert archived[0]["text"] == "one two three four five six"
    assert db.document_count() == 5
