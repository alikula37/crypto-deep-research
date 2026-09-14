"""Veri hizlandirma ve Faz 3 testleri: watchlist seed, drift, arsiv."""

import sqlite3
import time

from crypto_deep_research.learning.drift import (
    compute_drift,
    drift_summary,
    population_stability_index,
)
from crypto_deep_research.storage.archive import archive_runs
from crypto_deep_research.storage.db import Database


def _snapshot(db, run_id, coin, created_at, coverage, score):
    db.execute(
        """
        INSERT OR REPLACE INTO feature_snapshots
          (run_id, coin, created_at, coverage_ratio, weighted_score)
        VALUES (?, ?, ?, ?, ?)
        """,
        (run_id, coin, created_at, coverage, score),
    )


def test_seed_watchlist_only_missing(tmp_path):
    db = Database(tmp_path / "t.db")
    assert db.seed_watchlist() == 10
    assert db.seed_watchlist() == 0
    db.watchlist_remove("bitcoin")
    assert db.seed_watchlist() == 0  # liste bos degil
    assert db.seed_watchlist(only_if_empty=False) == 1
    coins = {entry["coin"] for entry in db.watchlist_list()}
    assert "bitcoin" in coins and len(coins) == 10
    assert all(entry["auto_run"] for entry in db.watchlist_list())


def test_psi_identical_and_shifted():
    base = [0.0] * 50 + [0.1] * 50
    assert population_stability_index(base, base) == 0.0
    shifted = [0.5] * 100
    psi = population_stability_index(base, shifted)
    assert psi is not None and psi > 0.25
    assert population_stability_index([0.0], [1.0]) is None  # yetersiz ornek


def test_compute_drift_flags_coverage_drop(tmp_path):
    db = Database(tmp_path / "t.db")
    now = time.time()
    day = 86_400
    for index in range(40):
        _snapshot(db, f"old{index}", "bitcoin", now - 60 * day - index, 0.90, 0.01 * index)
    for index in range(40):
        _snapshot(db, f"new{index}", "bitcoin", now - 3 * day - index, 0.55, 0.01 * index)
    entries = compute_drift(db, now=now, window_days=30, baseline_days=90)
    coverage = next(entry for entry in entries if entry["metric"] == "coverage_delta")
    assert coverage["alarm"] is True
    assert coverage["delta"] < -0.2
    psi_entry = next((entry for entry in entries if entry["metric"] == "score_psi"), None)
    assert psi_entry is not None
    assert db.drift_latest(), "drift satirlari kaydedilmeli"
    summary = drift_summary(entries)
    assert summary["degraded"] is True and summary["alarm_count"] >= 1


def test_archive_export_and_delete(tmp_path):
    db = Database(tmp_path / "t.db")
    now = time.time()
    db.execute(
        "INSERT INTO runs (run_id, coin, created_at, payload) VALUES (?, ?, ?, ?)",
        ("old_run", "bitcoin", now - 40 * 86_400, "{}"),
    )
    db.execute(
        "INSERT INTO runs (run_id, coin, created_at, payload) VALUES (?, ?, ?, ?)",
        ("new_run", "bitcoin", now, "{}"),
    )
    db.execute(
        "INSERT INTO reports (name, run_id, coin, created_at, markdown, meta) VALUES (?, ?, ?, ?, ?, ?)",
        ("OLD_REPORT", "old_run", "bitcoin", now - 40 * 86_400, "# eski", None),
    )
    archive_path = tmp_path / "archive" / "runs.sqlite"
    result = archive_runs(
        db, archive_path=archive_path, older_than_days=30, delete=True, now=now
    )
    assert result["runs"] == 1 and result["reports"] == 1
    assert result["deleted"] == 2
    remaining = db.query("SELECT run_id FROM runs")
    assert [row["run_id"] for row in remaining] == ["new_run"]

    connection = sqlite3.connect(archive_path)
    try:
        archived_runs = connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
        archived_reports = connection.execute("SELECT COUNT(*) FROM reports").fetchone()[0]
    finally:
        connection.close()
    assert archived_runs == 1 and archived_reports == 1
