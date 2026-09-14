"""Tarihsel seri ve ekonomik metrik testleri (B2)."""

from crypto_deep_research.learning.dataset import build_dataset, vector_for
from crypto_deep_research.learning.history import (
    EXTENDED_ITEM_IDS,
    asof,
    change_pct,
    extended_features_for_day,
)
from crypto_deep_research.learning.models import economic_metrics


def test_asof_and_change_pct():
    series = {"2026-01-01": 100.0, "2026-01-05": 110.0}
    assert asof(series, "2026-01-05") == 110.0
    assert asof(series, "2026-01-03") == 100.0  # 2 gun geriye
    assert asof(series, "2026-02-01") is None
    assert change_pct(series, "2026-01-05", 4) == 10.0
    assert change_pct(series, "2026-01-05", 30) is None


def test_extended_features_for_day():
    bundle = {
        "funding": {f"2026-01-{day:02d}": 0.0001 * (day % 3) for day in range(1, 31)},
        "perp_close": {"2026-01-30": 101.0},
        "macro_DXY": {"2026-01-30": 104.0, "2026-01-23": 100.0},
        "macro_GOLD": {},
        "macro_SPX": {"2026-01-30": 5000.0, "2026-01-23": 4900.0},
        "macro_US10Y": {"2026-01-30": 4.2},
        "macro_VIX": {"2026-01-30": 18.0, "2026-01-23": 20.0},
        "fng": {"2026-01-30": 55.0, "2026-01-23": 40.0},
        "stablecoin_total": {"2026-01-30": 200e9, "2026-01-23": 190e9, "2025-12-31": 180e9},
    }
    values = extended_features_for_day(bundle, 100.0, "2026-01-30")
    ids = EXTENDED_ITEM_IDS
    assert values[ids["basis_pct"]] == 1.0
    assert values[ids["dxy_7d"]] == 4.0
    assert values[ids["spx_7d"]] == round((5000 / 4900 - 1) * 100, 4)
    assert values[ids["us10y"]] == 4.2
    assert values[ids["fng"]] == 55.0
    assert values[ids["fng_7d"]] == round((55 / 40 - 1) * 100, 4)
    assert values[ids["stable_7d"]] == round((200 / 190 - 1) * 100, 4)
    assert ids["funding_z7"] in values


def test_vector_for_and_dataset_with_extended():
    snapshot = {
        "weighted_score": 0.1, "signal_strength": 0.2, "coverage_ratio": 0.5,
        "coverage_weighted": 0.4, "score_dispersion": 0.3, "confidence_mean": 0.5,
        "atr_pct": 2.0, "n_ok": 10, "n_partial": 0, "n_no_data": 56, "n_error": 0,
        "category_scores": '{"Teknik": 0.2}',
    }
    vector = vector_for(snapshot, {101: 0.01, 111: 50.0})
    assert len(vector) == 25
    assert vector[-1] == round(2 / 14, 4)  # varlik orani
    rows = [{**snapshot, "return_pct": -1.0, "run_id": "r1", "target_date": "2026-01-02", "coin": "bitcoin"}]
    dataset = build_dataset(rows, {"r1": {101: 0.01}})
    assert dataset["y"] == [0]
    assert dataset["returns"] == [-1.0]
    assert len(dataset["feature_names"]) == 25


def test_economic_metrics_direction():
    returns = [1.0, -1.0] * 20
    good = [0.9 if value > 0 else 0.1 for value in returns]
    metrics = economic_metrics(good, returns, horizon_days=1)
    assert metrics["net_sharpe"] is not None and metrics["net_sharpe"] > 0
    assert metrics["active_ratio"] == 1.0
    bad = [0.1 if value > 0 else 0.9 for value in returns]
    assert economic_metrics(bad, returns, horizon_days=1)["net_sharpe"] < 0
    neutral = [0.5] * len(returns)
    assert economic_metrics(neutral, returns, horizon_days=1)["active_ratio"] == 0.0
