"""Onbellek ve depolama testleri."""

import time

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
