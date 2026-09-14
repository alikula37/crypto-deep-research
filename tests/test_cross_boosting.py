"""Kesitsel ozellikler ve gradyan artirma testleri (B3)."""

import time

from crypto_deep_research.learning.boosting import BoostedTrees
from crypto_deep_research.learning.cross_section import (
    beta_corr,
    compute_cross_section,
    percentile_rank,
)
from crypto_deep_research.learning.models import auc_score
from crypto_deep_research.learning.trainer import predict_snapshot
from crypto_deep_research.storage.db import Database


def test_percentile_rank():
    values = [10.0, 20.0, 30.0, 40.0]
    assert percentile_rank(values, 40.0) == 1.0
    assert percentile_rank(values, 10.0) == 0.0
    assert percentile_rank(values, 25.0) == round(2 / 3, 4)  # 10 ve 20 degerin altinda
    assert percentile_rank([], 1.0) is None


def test_beta_corr_synthetic():
    btc = {}
    coin = {}
    price_btc, price_coin = 100.0, 50.0
    start = time.time() - 40 * 86_400
    for index in range(40):
        day = time.strftime("%Y-%m-%d", time.gmtime(start + index * 86_400))
        btc[day] = price_btc
        coin[day] = price_coin
        price_btc *= 1 + (0.01 if index % 2 == 0 else -0.005)
        price_coin *= 1 + 2 * (0.01 if index % 2 == 0 else -0.005)
    day = max(btc)
    beta, corr = beta_corr(coin, btc, day)
    assert beta is not None and beta > 1.5  # coin daha oynak
    assert corr is not None and corr > 0.9  # ayni yonde


def test_compute_cross_section_writes_pseudo_items(tmp_path):
    db = Database(tmp_path / "t.db")
    now = time.time()
    for offset in range(40):
        created = now - (40 - offset) * 86_400
        db.execute(
            """
            INSERT OR REPLACE INTO feature_snapshots (run_id, coin, created_at, current_price, source)
            VALUES (?, ?, ?, ?, 'backfill')
            """,
            (f"bf_btc_{offset}", "bitcoin", created, 60000 + offset * 100),
        )
        db.execute(
            """
            INSERT OR REPLACE INTO feature_snapshots (run_id, coin, created_at, current_price, source)
            VALUES (?, ?, ?, ?, 'backfill')
            """,
            (f"bf_sol_{offset}", "solana", created, 100 + offset * 2),
        )
    result = compute_cross_section(db, source="backfill")
    assert result["written"] > 0
    rows = db.query(
        "SELECT item_id, COUNT(*) n FROM item_features WHERE item_id >= 121 GROUP BY item_id"
    )
    ids = {row["item_id"] for row in rows}
    assert 121 in ids and 124 in ids and 125 in ids
    extended = db.extended_features(["bf_btc_39"])
    assert extended and any(item_id >= 121 for item_id in extended["bf_btc_39"])


def test_boosting_learns_nonlinear_pattern():
    # XOR-benzeri desen: lojistik dogrusal model ogrenemez, agac ogrenir
    X = []
    y = []
    for a in range(20):
        for b in range(20):
            X.append([a / 20, b / 20, (a % 3) / 3, (b % 5) / 5])
            y.append(1 if (a > 10) != (b > 10) else 0)
    split = 300
    model = BoostedTrees(rounds=120, learning_rate=0.15, max_depth=3, min_leaf=10).fit(
        X[:split], y[:split]
    )
    probabilities = model.predict_proba(X[split:])
    auc = auc_score(y[split:], probabilities)
    assert auc is not None and auc > 0.9
    # parametre yuvarlamasi tahmin yolunda calisiyor
    restored = BoostedTrees.from_params(model.to_params())
    assert abs(restored.predict_proba([X[-1]])[0] - probabilities[-1]) < 1e-9


def test_predict_snapshot_isotonic_dispatch():
    snapshot = {
        "weighted_score": 0.2, "signal_strength": 0.2, "coverage_ratio": 0.9,
        "coverage_weighted": 0.8, "score_dispersion": 0.3, "confidence_mean": 0.6,
        "atr_pct": 2.0, "n_ok": 60, "n_partial": 2, "n_no_data": 4, "n_error": 0,
        "category_scores": '{"Teknik": 0.3}',
    }
    # kimlik agirliklar + kimlik izotonik: cikti ham olasiliga esit olmali
    weights = [0.0] * 34 + [1.0]
    params = {
        "algorithm": "logreg",
        "logistic": {
            "weights": weights,
            "intercept": 0.0,
            "scaler": {"mean": [0.0] * 35, "std": [1.0] * 35},
        },
        "calibration": {"type": "isotonic", "points": [[0.0, 0.1], [1.0, 0.9]]},
    }
    probability = predict_snapshot(snapshot, params)
    assert 0.1 <= probability <= 0.9
