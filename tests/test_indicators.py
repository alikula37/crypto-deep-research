"""Indikator ve seviye hesaplamalari testleri (sentetik veri)."""

from datetime import datetime, timedelta, timezone

from crypto_deep_research.analysis.indicators import (
    atr,
    bollinger,
    candle_patterns,
    compute_levels,
    fibonacci_levels,
    find_pivots,
    indicator_snapshot,
    macd,
    rsi,
    to_dataframe,
    volume_profile,
)
from crypto_deep_research.models import Kline


def make_klines(n: int = 300, start: float = 100.0) -> list[Kline]:
    klines = []
    price = start
    base = datetime(2025, 1, 1, tzinfo=timezone.utc)
    for i in range(n):
        price = price * (1 + 0.002 * ((i % 7) - 3))
        klines.append(
            Kline(
                ts=base + timedelta(days=i),
                open=price * 0.99,
                high=price * 1.02,
                low=price * 0.98,
                close=price,
                volume=1000 + i * 10,
            )
        )
    return klines


def test_dataframe_and_indicators():
    df = to_dataframe(make_klines())
    assert len(df) == 300
    assert 0 <= rsi(df["close"]).iloc[-1] <= 100
    macd_line, signal_line, histogram = macd(df["close"])
    assert len(macd_line) == len(df)
    middle, upper, lower, width, position = bollinger(df["close"])
    assert upper.iloc[-1] >= middle.iloc[-1] >= lower.iloc[-1]
    assert atr(df).iloc[-1] > 0
    snapshot = indicator_snapshot(df)
    assert snapshot["price"] > 0
    assert "rsi_14" in snapshot


def test_pivots_and_levels():
    df = to_dataframe(make_klines())
    pivots = find_pivots(df)
    assert pivots["support"] and pivots["resistance"]
    current = float(df["close"].iloc[-1])
    levels = compute_levels(df, current)
    assert levels["swing_high"] >= levels["swing_low"]
    assert "fibonacci" in levels
    assert levels["nearest_support"] is not None


def test_fibonacci_levels_ordering():
    fib = fibonacci_levels(200.0, 100.0)
    assert fib["0.0"] == 200.0
    assert fib["1.0"] == 100.0
    assert fib["0.5"] == 150.0
    assert fib["0.618"] == 200 - 0.618 * 100


def test_volume_profile_shares_sum_to_one():
    df = to_dataframe(make_klines())
    profile = volume_profile(df, bins=10)
    assert profile
    total_share = sum(bucket["share"] for bucket in profile)
    assert abs(total_share - 1.0) < 0.05


def test_candle_patterns_returns_list():
    df = to_dataframe(make_klines())
    patterns = candle_patterns(df)
    assert isinstance(patterns, list)
