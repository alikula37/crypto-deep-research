"""Tarihsel replay testleri: bilesen skorlari, ornek uretimi, backfill kaydi."""

from datetime import datetime, timedelta, timezone

import pandas as pd

from crypto_deep_research.analysis.indicators import to_dataframe
from crypto_deep_research.deep_research.engine import compute_group_factors
from crypto_deep_research.deep_research.registry import load_registry
from crypto_deep_research.learning.replay import (
    HORIZONS,
    _build_sample,
    compute_component_scores,
)
from crypto_deep_research.learning.trainer import train_horizon
from crypto_deep_research.models import Kline
from crypto_deep_research.storage.db import Database


def _synthetic_klines(days: int = 260, drift: float = 0.002) -> list[Kline]:
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    price = 100.0
    klines = []
    for index in range(days):
        price *= 1 + drift + (0.004 if index % 7 == 0 else -0.001)
        klines.append(
            Kline(
                ts=start + timedelta(days=index),
                open=price * 0.995,
                high=price * 1.01,
                low=price * 0.99,
                close=price,
                volume=1000 + index * 3,
            )
        )
    return klines


def _df(klines) -> pd.DataFrame:
    return to_dataframe(klines)


def test_component_scores_on_uptrend():
    df = _df(_synthetic_klines())
    components = compute_component_scores(df)
    assert set(components["scores"]) == {1, 7, 14, 15, 16, 18, 19, 21, 24, 35, 36, 37, 48}
    assert components["price"] > 100
    assert components["atr_pct"] is not None
    assert components["scores"][1] > 0, "yukselen trendde teknik skor pozitif olmali"
    assert components["scores"][37] > 0, "yukselen trendde getiri t-istatistigi pozitif olmali"


def test_build_sample_uses_only_past_and_labels_forward():
    df = _df(_synthetic_klines())
    closes = df["close"].values.astype(float)
    timestamps = [int(ts.timestamp()) for ts in df.index]
    specs = load_registry()
    factors = compute_group_factors(specs)
    index = 225
    components = compute_component_scores(df.iloc[: index + 1])
    sample = _build_sample("bitcoin", "BTC", timestamps[index], components, closes, index, specs, factors)
    assert sample is not None
    assert sample["run_id"] == f"bf_bitcoin_{timestamps[index]}"
    assert len(sample["items"]) == 13
    assert len(sample["outcomes"]) == len(HORIZONS)
    assert sample["weighted_score"] is not None
    # yukselen seride ileri getiri pozitif; yon 'up' ise isabet 1 olmali
    for outcome in sample["outcomes"]:
        if outcome[11] == "up":
            assert outcome[9] > 0 and outcome[10] == 1
    # kesim sonrasi veri kullanilmamali: skorlar kesim fiyatindan turetilmis olmali
    assert sample["current_price"] == closes[index]


def test_backfill_batch_and_training(tmp_path):
    db = Database(tmp_path / "t.db")
    specs = load_registry()
    factors = compute_group_factors(specs)
    base = datetime(2025, 1, 1, tzinfo=timezone.utc)
    samples = []
    for index in range(45):
        rise = index % 2 == 0
        drift = 0.004 if rise else -0.004
        df = _df(_synthetic_klines(260, drift=drift))
        closes = df["close"].values.astype(float)
        timestamp = int((base + timedelta(days=index)).timestamp())
        components = compute_component_scores(df)
        sample = _build_sample("bitcoin", "BTC", timestamp, components, closes, 225, specs, factors)
        assert sample is not None
        # etiketi skorla uyumlu hale getir (yukselen seri -> pozitif skor)
        samples.append(sample)
    assert db.save_backfill_batch(samples) == 45
    rows = db.learning_rows(7, source="backfill")
    assert len(rows) == 45
    assert all(row["source"] == "backfill" for row in rows)
    assert db.learning_rows(7, source="live") == []

    result = train_horizon(db, 7, min_samples=30, source="backfill")
    assert result["status"] == "trained"
    assert result["model_status"] == "shadow", "backfill modeli otomatik aktiflesmemeli"
    assert result["model_id"].startswith("logreg_platt_bf")
    assert result["metrics"]["n_oos"] > 0
    model = db.model_get(7)
    assert model is not None and model["kind"] == "logreg_platt_bf"
