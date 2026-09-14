"""Ogrenme dongusu testleri: ozellik cikarimi, outcome etiketleri, kalibrasyon."""

from datetime import datetime, timezone

from crypto_deep_research.deep_research.engine import compute_group_factors
from crypto_deep_research.deep_research.registry import load_registry
from crypto_deep_research.learning.calibration import (
    calibration_table,
    heuristic_probability,
    wilson_interval,
)
from crypto_deep_research.learning.features import (
    build_pending_outcomes,
    extract_items,
    extract_run,
    persist_run,
)
from crypto_deep_research.models import CoinRef, ItemResult, ResearchRun
from crypto_deep_research.storage.db import Database


def _item(item_id, score, confidence=0.8, status="ok", category="Teknik", weight=None):
    specs = {spec.id: spec for spec in load_registry()}
    spec = specs[item_id]
    return ItemResult(
        item_id=item_id,
        title_tr=spec.title_tr,
        category=category or spec.category,
        weight=weight if weight is not None else spec.weight,
        key=f"item_{item_id}",
        title=spec.title_tr,
        status=status,
        score=score,
        confidence=confidence,
    )


def _run(items, score=0.12):
    return ResearchRun(
        run_id="run123456789",
        coin=CoinRef(id="bitcoin", symbol="btc", name="Bitcoin"),
        created_at=datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc),
        weighted_score=score,
        up_probability=54.2,
        down_probability=45.8,
        expected_low=60000.0,
        expected_high=70000.0,
        current_price=65000.0,
        items=items,
    )


def test_extract_run_counts_and_strength():
    specs = load_registry()
    items = [
        _item(1, 0.30),
        _item(7, 0.30),
        _item(31, -0.40, category="Zincir-Üstü"),
        _item(2, None, confidence=0.0, status="no_data"),
        _item(4, 0.0, confidence=0.2, status="partial"),
    ]
    factors = compute_group_factors(specs)
    features = extract_run(_run(items), specs, group_factors=factors)
    assert features["n_ok"] == 3
    assert features["n_no_data"] == 1
    assert features["n_partial"] == 1
    assert features["coverage_ratio"] == (3 + 0.5) / 5
    assert features["signal_strength"] is not None
    assert features["items_hash"]


def test_extract_items_contributions():
    specs = load_registry()
    items = [_item(1, 0.5), _item(2, None, confidence=0.0, status="no_data")]
    rows = extract_items(_run(items), group_factors=compute_group_factors(specs))
    assert len(rows) == 2
    assert rows[0]["contribution"] is not None
    assert rows[1]["contribution"] is None


def test_pending_outcomes_horizons_and_direction():
    items = [_item(1, 0.5)]
    rows = build_pending_outcomes(_run(items, score=0.2))
    assert [row["horizon_days"] for row in rows] == [1, 7, 30]
    assert all(row["direction_at_run"] == "up" for row in rows)
    assert rows[0]["target_date"] == "2026-09-11"
    assert rows[2]["target_date"] == "2026-10-10"
    neutral = build_pending_outcomes(_run(items, score=0.0))
    assert neutral[0]["direction_at_run"] == "neutral"


def test_heuristic_probability_bounds():
    assert heuristic_probability(0.0) == 50.0
    assert heuristic_probability(0.2) == 57.0
    assert heuristic_probability(5.0) == 95.0
    assert heuristic_probability(None) == 50.0


def test_wilson_interval_sanity():
    low, high = wilson_interval(50, 100)
    assert 0.39 < low < 0.41 and 0.59 < high < 0.61
    assert wilson_interval(0, 0) == (None, None)


def test_calibration_table_metrics():
    rows = []
    for index in range(120):
        score = 0.5 if index % 2 == 0 else -0.5
        hit = 1 if (score > 0 and index % 3 != 0) else (0 if score < 0 and index % 3 != 0 else None)
        rows.append({"f_score": score, "hit": hit})
    table = calibration_table(rows)
    assert table["n"] > 0
    assert table["brier"] is not None
    assert table["baseline_brier"] is not None
    assert table["ece"] is not None
    assert 0 <= table["ece"] <= 1
    assert table["auc"] is not None


def test_persist_run_is_idempotent(tmp_path):
    db = Database(tmp_path / "t.db")
    specs = load_registry()
    run = _run([_item(1, 0.4), _item(2, -0.2, category="Temel")])
    factors = compute_group_factors(specs)
    assert persist_run(db, run, specs, group_factors=factors) is True
    assert persist_run(db, run, specs, group_factors=factors) is True
    assert db.query("SELECT COUNT(*) AS n FROM feature_snapshots")[0]["n"] == 1
    assert db.query("SELECT COUNT(*) AS n FROM item_features")[0]["n"] == 2
    assert db.query("SELECT COUNT(*) AS n FROM outcomes")[0]["n"] == 3
    missing = db.runs_missing_features()
    assert missing == []
