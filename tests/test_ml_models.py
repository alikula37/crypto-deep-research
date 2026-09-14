"""ML cekirdegi testleri: modeller, purged CV, veri seti ve egitici."""

from datetime import datetime, timedelta, timezone

import pytest

from crypto_deep_research.deep_research.engine import compute_group_factors
from crypto_deep_research.deep_research.registry import load_registry
from crypto_deep_research.learning.dataset import build_dataset, row_features
from crypto_deep_research.learning.features import persist_run
from crypto_deep_research.learning.models import (
    LogisticModel,
    auc_score,
    brier_score,
    isotonic_apply,
    isotonic_fit,
    logit,
    platt_apply,
    platt_fit,
    purged_walk_forward,
)
from crypto_deep_research.learning.trainer import train_horizon
from crypto_deep_research.models import CoinRef, ItemResult, ResearchRun
from crypto_deep_research.storage.db import Database


def test_standardizer_and_logistic_learns():
    X = [[-2.0], [-1.5], [-1.0], [1.0], [1.5], [2.0]] * 6
    y = [0, 0, 0, 1, 1, 1] * 6
    model = LogisticModel(l2=0.5, iterations=800).fit(X, y)
    probes = model.predict_proba([[-2.0], [2.0]])
    assert probes[0] < 0.4 < 0.6 < probes[1]
    params = model.to_params()
    restored = LogisticModel.from_params(params)
    assert abs(restored.predict_proba([[2.0]])[0] - probes[1]) < 1e-9


def test_platt_and_isotonic_calibration():
    scores = [-2.0, -1.0, -0.5, 0.5, 1.0, 2.0] * 5
    y = [0, 0, 1, 0, 1, 1] * 5
    a, b = platt_fit(scores, y)
    calibrated = platt_apply(a, b, scores)
    assert all(0.0 < value < 1.0 for value in calibrated)
    points = isotonic_fit(scores, y)
    values = [value for _, value in points]
    assert values == sorted(values), "izotonik esleme monoton olmali"
    interpolated = isotonic_apply(points, [-3.0, 0.0, 3.0])
    assert interpolated[0] <= interpolated[1] <= interpolated[2]


def test_metrics_bounds():
    assert auc_score([0, 1], [0.2, 0.8]) == 1.0
    assert auc_score([0, 1], [0.8, 0.2]) == 0.0
    assert brier_score([1, 0], [1.0, 0.0]) == 0.0
    assert logit(0.5) == pytest.approx(0.0, abs=1e-9)


def test_purged_walk_forward_excludes_overlap():
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    dates = [(base + timedelta(days=index)).date().isoformat() for index in range(60)]
    windows = purged_walk_forward(dates, horizon_days=7, folds=3, min_train=8)
    assert windows, "pencereler uretilmeli"
    for train_idx, test_idx in windows:
        test_start = dates[test_idx[0]]
        for index in train_idx:
            assert dates[index] < test_start
        # purge: hedef tarihi test baslangicini asan egitim ornegi kalmamali
        assert len(train_idx) < test_idx[0]


def test_row_features_from_snapshot():
    row = {
        "weighted_score": 0.2,
        "signal_strength": 0.3,
        "coverage_ratio": 0.9,
        "coverage_weighted": 0.8,
        "score_dispersion": 0.3,
        "confidence_mean": 0.5,
        "atr_pct": 2.5,
        "n_ok": 50,
        "n_partial": 10,
        "n_no_data": 5,
        "n_error": 1,
        "category_scores": '{"Teknik": 0.4, "Makro": -0.2}',
    }
    features = row_features(row)
    assert features["no_data_ratio"] == pytest.approx(5 / 66, abs=1e-4)
    assert features["category_spread"] == pytest.approx(0.6)
    dataset = build_dataset([{**row, "return_pct": 1.5, "target_date": "2026-01-02", "coin": "bitcoin", "run_id": "r1"}])
    assert dataset["y"] == [1]
    assert len(dataset["X"][0]) == 35  # 10 temel + 24 genisletilmis/kesitsel + varlik orani


def _synthetic_run(index: int, score: float) -> ResearchRun:
    specs = load_registry()
    items = []
    for item_id in (1, 2, 31):
        items.append(
            ItemResult(
                item_id=item_id,
                title_tr=specs[item_id - 1].title_tr,
                category=specs[item_id - 1].category,
                weight=1.0,
                key=f"item_{item_id}",
                title=specs[item_id - 1].title_tr,
                status="ok",
                score=score,
                confidence=0.9,
            )
        )
    created = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=index)
    return ResearchRun(
        run_id=f"run{index:04d}",
        coin=CoinRef(id="bitcoin", symbol="btc", name="Bitcoin"),
        created_at=created,
        weighted_score=score,
        up_probability=50 + 35 * score,
        down_probability=50 - 35 * score,
        expected_low=100.0,
        expected_high=110.0,
        current_price=105.0,
        items=items,
    )


def test_trainer_smoke_on_synthetic_data(tmp_path):
    db = Database(tmp_path / "t.db")
    specs = load_registry()
    factors = compute_group_factors(specs)
    for index in range(48):
        score = 0.35 if index % 2 == 0 else -0.35
        run = _synthetic_run(index, score)
        assert persist_run(db, run, specs, group_factors=factors) is True
        return_pct = 2.0 if score > 0 else -2.0
        db.outcome_mark_filled(
            run.run_id,
            7,
            exit_price=run.current_price * (1 + return_pct / 100),
            return_pct=return_pct,
            hit=1 if return_pct > 0 else 0,
            price_source="test",
        )
    result = train_horizon(db, 7, min_samples=30)
    assert result["status"] == "trained"
    assert result["model_status"] == "shadow"  # n<200 -> asla aktif olmaz
    assert result["metrics"]["auc"] is not None and result["metrics"]["auc"] > 0.8
    assert result["metrics"]["brier"] < result["metrics"]["baseline_brier"]
    assert result["predictions_written"] == 48
    assert db.model_get(7) is not None
