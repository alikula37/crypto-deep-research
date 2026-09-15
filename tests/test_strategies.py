"""Strateji tarayici testleri: metrikler, TSMOM, kesitsel momentum, carry."""

import pandas as pd

from crypto_deep_research.learning.strategies import carry, metrics, tsmom, xsmom


def _frame(prices: list[float]) -> pd.DataFrame:
    index = pd.date_range("2025-01-01", periods=len(prices), freq="D", tz="UTC")
    close = pd.Series(prices, index=index, dtype=float)
    return pd.DataFrame(
        {"close": close, "high": close * 1.01, "low": close * 0.99, "open": close, "volume": 1000.0}
    )


def test_metrics_basic():
    daily = [0.01] * 100
    stats = metrics(daily)
    assert stats["sharpe"] is None or stats["sharpe"] > 0
    assert stats["total_return"] > 0
    losing = [-0.01] * 100
    assert metrics(losing)["max_drawdown"] < -0.5


def test_tsmom_follows_uptrend():
    prices = [100 * (1.01**index) for index in range(200)]
    daily = tsmom(_frame(prices), lookback=30, cost_bps=6)
    stats = metrics(daily)
    assert stats["total_return"] > 0.1, "yukselen trendde TSMOM pozitif olmali"
    falling = [100 * (0.99**index) for index in range(200)]
    down_stats = metrics(tsmom(_frame(falling), lookback=30))
    assert down_stats["total_return"] > 0.1, "dusen trendde short ile kazanmali"


def test_xsmom_ranks_relative_strength():
    frames = {}
    for index in range(6):
        growth = 1.012 - index * 0.004
        frames[f"c{index}"] = _frame([100 * (growth**step) for step in range(260)])
    daily, members = xsmom(frames, lookback=30, top_k=2, rebalance=30, cost_bps=6)
    stats = metrics(daily)
    assert members, "yeniden dengeleme gunleri olmali"
    assert stats["total_return"] > 0, "guclu coinleri long tutan strateji pozitif olmali"


def test_carry_collects_funding():
    funding = {f"2025-01-{day:02d}": 0.0002 for day in range(1, 31)}
    daily = carry(funding, cost_bps=6, horizon_days=30)
    assert len(daily) == 30
    assert daily[0] < 0  # ilk gun iki bacak maliyeti
    assert abs(daily[1] - 0.0002) < 1e-9  # short perp fonlamayi alir (pozitif)
    assert daily[-1] > 0


def test_portfolio_diversifies():
    from crypto_deep_research.learning.strategies import scan

    frames = {}
    for index in range(6):
        growth = 1.008 + index * 0.002
        prices = [100 * (growth**step) for step in range(300)]
        dates = pd.date_range("2024-06-01", periods=300, freq="D", tz="UTC")
        close = pd.Series(prices, index=dates)
        frames[f"c{index}"] = pd.DataFrame(
            {"close": close, "high": close, "low": close,
             "open": close, "volume": 1000.0}
        )
    results = {row["params"]: row for row in scan(frames, {}) if row.get("sharpe") is not None}
    portfolio = next(row for key, row in results.items() if key.startswith("BREAK esit"))
    single = next(row for key, row in results.items() if key.startswith("c0 20/10"))
    assert portfolio["sharpe"] >= single["sharpe"]
