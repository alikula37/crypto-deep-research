"""Kesitsel portfoy backtest testleri."""

from datetime import datetime, timedelta, timezone

from crypto_deep_research.learning.models import EVALUATION_PROTOCOL
from crypto_deep_research.learning.portfolio import run_backtest, select_rebalance_dates
from crypto_deep_research.storage.db import Database


def test_select_rebalance_dates():
    days = [(datetime(2026, 1, 1) + timedelta(days=index)).date().isoformat() for index in range(90)]
    chosen = select_rebalance_dates(days, 30)
    assert chosen[0] == "2026-01-01"
    assert len(chosen) == 3
    assert chosen[1] == "2026-01-31"


def _seed(db, coins, days, noise_scale=0.0, evaluation_protocol=EVALUATION_PROTOCOL):
    db.model_save(
        {
            "model_id": "test",
            "kind": "test",
            "horizon_days": 30,
            "status": "shadow",
            "evaluation_protocol": evaluation_protocol,
        }
    )
    base = datetime(2025, 1, 1, tzinfo=timezone.utc)
    for day_index in range(days):
        created = base + timedelta(days=day_index * 30)
        for coin_index, coin in enumerate(coins):
            run_id = f"{coin}_{day_index}"
            # Olasilik yuksek -> gelecek getiri yuksek (test verisi)
            probability = 0.9 - coin_index * 0.05
            forward = (5.0 - coin_index * 2.0) + noise_scale * ((day_index % 3) - 1)
            db.execute(
                "INSERT OR REPLACE INTO feature_snapshots (run_id, coin, created_at, current_price, source)"
                " VALUES (?, ?, ?, ?, 'backfill')",
                (run_id, coin, created.timestamp(), 100 + coin_index),
            )
            db.execute(
                "INSERT OR REPLACE INTO predictions (run_id, horizon_days, model_id, probability_up, probability_down, is_shadow, created_at, is_oos)"
                " VALUES (?, 30, 'test', ?, ?, 1, ?, 1)",
                (run_id, probability * 100, (1 - probability) * 100, created.timestamp()),
            )
            db.execute(
                "INSERT OR REPLACE INTO outcomes"
                " (run_id, horizon_days, coin, entry_at, target_date, due_at, return_pct, status, source)"
                " VALUES (?, 30, ?, ?, ?, ?, ?, 'filled', 'backfill')",
                (
                    run_id, coin, created.timestamp(),
                    (created + timedelta(days=30)).date().isoformat(),
                    (created + timedelta(days=30)).timestamp(), forward,
                ),
            )


def test_backtest_selects_winners(tmp_path):
    db = Database(tmp_path / "t.db")
    coins = ["bitcoin", "ethereum", "solana", "cardano", "polkadot", "chainlink"]
    _seed(db, coins, 6)
    result = run_backtest(db, horizon=30, top_k=2, cost_bps=10, rebalance_days=30)
    assert result["status"] == "ok"
    assert result["periods"] == 5
    # Ust-k sepeti esit agirlikli evreni ve alt-k'yi yenmeli (tek varlik BTC'yi degil)
    assert result["equity"]["top_k"] > result["equity"]["equal_weight"]
    assert result["equity"]["long_short"] > 1.0
    assert result["avg_spread_pct"] > 0
    assert result["hit_rate"] == 1.0
    assert result["net_sharpe"]["top_k"] is not None


def test_backtest_excludes_legacy_oos_predictions(tmp_path):
    db = Database(tmp_path / "t.db")
    coins = ["bitcoin", "ethereum", "solana", "cardano", "polkadot", "chainlink"]
    _seed(db, coins, 6, evaluation_protocol=None)
    result = run_backtest(db, horizon=30, top_k=2, source="backfill")
    assert result["status"] == "no_data"


def test_backtest_cost_reduces_equity(tmp_path):
    db = Database(tmp_path / "t.db")
    coins = ["bitcoin", "ethereum", "solana", "cardano", "polkadot", "chainlink"]
    _seed(db, coins, 6)
    free = run_backtest(db, horizon=30, top_k=2, cost_bps=0, rebalance_days=30)
    costly = run_backtest(db, horizon=30, top_k=2, cost_bps=100, rebalance_days=30)
    assert costly["equity"]["top_k"] < free["equity"]["top_k"]


def test_backtest_without_oos_predictions(tmp_path):
    db = Database(tmp_path / "t.db")
    result = run_backtest(db, horizon=30)
    assert result["status"] == "no_data"
