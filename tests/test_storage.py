"""Onbellek ve depolama testleri."""

import sqlite3
import time

from crypto_deep_research.learning.models import EVALUATION_PROTOCOL
from crypto_deep_research.models import NewsArticle
from crypto_deep_research.storage.db import Database, stable_key


def test_cache_set_get_with_ttl(tmp_path):
    db = Database(tmp_path / "cache.db")
    key = stable_key("provider", "http://example.com", {"a": 1})
    db.cache_set(key, "provider", "http://example.com", {"value": 42}, ttl=60)
    cached = db.cache_get(key)
    assert cached is not None
    payload, fresh = cached
    assert payload == {"value": 42}
    assert fresh is True
    db.cache_clear("provider")
    assert db.cache_get(key) is None


def test_cache_stale_when_ttl_expired(tmp_path):
    db = Database(tmp_path / "cache.db")
    key = stable_key("p", "u")
    db.cache_set(key, "p", "u", {"x": 1}, ttl=-1)
    payload, fresh = db.cache_get(key)
    assert payload == {"x": 1}
    assert fresh is False


def test_articles_roundtrip(tmp_path):
    db = Database(tmp_path / "news.db")
    articles = [
        NewsArticle(
            title="Bitcoin ETF inflow",
            url="https://example.com/a",
            source="Test",
            sentiment=0.5,
        )
    ]
    assert db.save_articles("bitcoin", articles) == 1
    loaded = db.get_articles("bitcoin")
    assert loaded and loaded[0].title == "Bitcoin ETF inflow"


def test_document_fts_search(tmp_path):
    db = Database(tmp_path / "docs.db")
    db.save_document("doc1", "bitcoin", "news", "Test", None, "Bitcoin likidasyon haritasi analizi")
    db.save_document("doc2", "ethereum", "news", "Test", None, "Ethereum gas ucretleri dusuyor")
    results = db.search_documents("likidasyon", coin="bitcoin")
    assert len(results) == 1
    assert results[0]["id"] == "doc1"


def test_metric_history(tmp_path):
    db = Database(tmp_path / "metrics.db")
    db.record_metric("bitcoin", "rank", 1.0, ts=time.time() - 100)
    db.record_metric("bitcoin", "rank", 2.0)
    history = db.metric_history("bitcoin", "rank")
    assert len(history) == 2
    assert history[0]["value"] == 2.0


def test_model_registry_migrates_legacy_rows_without_protocol(tmp_path):
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as connection:
        connection.execute(
            """CREATE TABLE model_registry (
                 model_id TEXT PRIMARY KEY, kind TEXT NOT NULL, horizon_days INTEGER NOT NULL,
                 status TEXT NOT NULL DEFAULT 'shadow', trained_at REAL, train_rows INTEGER,
                 feature_schema_version INTEGER NOT NULL DEFAULT 1, params TEXT, metrics TEXT, notes TEXT
               )"""
        )
        connection.execute(
            "INSERT INTO model_registry (model_id, kind, horizon_days, status) "
            "VALUES ('legacy', 'logreg_platt', 7, 'active')"
        )

    db = Database(path)
    legacy = db.model_get(7)
    assert legacy is not None and legacy["evaluation_protocol"] is None
    assert db.model_get(7, evaluation_protocol=EVALUATION_PROTOCOL) is None
    db.model_save(
        {
            "model_id": "holdout",
            "kind": "logreg_platt",
            "horizon_days": 7,
            "status": "shadow",
            "evaluation_protocol": EVALUATION_PROTOCOL,
        }
    )
    selected = db.model_get(7, evaluation_protocol=EVALUATION_PROTOCOL)
    assert selected is not None and selected["model_id"] == "holdout"
