"""Takip listesi testleri: DB kayitlari ve otomatik kosu zamanlamasi."""

from crypto_deep_research.api.app import _due_watchlist
from crypto_deep_research.storage.db import Database


def test_watchlist_crud(tmp_path):
    db = Database(tmp_path / "test.db")
    db.watchlist_add("bitcoin", symbol="BTC", name="Bitcoin", profile="conservative")
    rows = db.watchlist_list()
    assert len(rows) == 1
    assert rows[0]["symbol"] == "BTC"
    assert rows[0]["profile"] == "conservative"
    assert rows[0]["auto_run"] is True

    db.watchlist_add("bitcoin", profile="aggressive", auto_run=False)
    entry = db.watchlist_get("bitcoin")
    assert entry["profile"] == "aggressive"
    assert bool(entry["auto_run"]) is False

    db.watchlist_remove("bitcoin")
    assert db.watchlist_list() == []


def test_due_watchlist_selection():
    now = 1_800_000_000.0
    entries = [
        {"coin": "btc", "auto_run": True, "last_run_at": now - 25 * 3600},
        {"coin": "eth", "auto_run": True, "last_run_at": now - 2 * 3600},
        {"coin": "sol", "auto_run": False, "last_run_at": 0},
        {"coin": "ada", "auto_run": True, "last_run_at": None},
    ]
    due = [entry["coin"] for entry in _due_watchlist(entries, now, 24)]
    assert due == ["btc", "ada"]


def test_watchlist_get_normalizes_auto_run_bool(tmp_path):
    db = Database(tmp_path / "test.db")
    db.watchlist_add("bitcoin", auto_run=False)
    entry = db.watchlist_get("bitcoin")
    assert entry["auto_run"] is False
    db.watchlist_add("bitcoin", auto_run=True)
    assert db.watchlist_get("bitcoin")["auto_run"] is True
