"""Isabet (backtest) hesaplama testleri - ag erisimi olmadan."""

from datetime import date

from crypto_deep_research.deep_research.accuracy import (
    aggregate,
    close_for_date,
    evaluate_run,
)

CLOSES = {
    date(2026, 1, 10): 100.0,
    date(2026, 1, 11): 105.0,
    date(2026, 1, 17): 110.0,
    date(2026, 2, 9): 90.0,
}


def _run(score, price=100.0, ts=date(2026, 1, 10)):
    from datetime import datetime, timezone

    return {
        "run_id": "r1",
        "coin": "bitcoin",
        "symbol": "BTC",
        "created_at": datetime(ts.year, ts.month, ts.day, tzinfo=timezone.utc).timestamp(),
        "weighted_score": score,
        "current_price": price,
    }


def test_directional_hits_and_returns():
    outcome = evaluate_run(_run(0.4), CLOSES)
    assert outcome["returns_pct"]["1"] == 5.0
    assert outcome["returns_pct"]["7"] == 10.0
    assert outcome["returns_pct"]["30"] == -10.0
    assert outcome["hits"]["1"] is True
    assert outcome["hits"]["7"] is True
    assert outcome["hits"]["30"] is False


def test_negative_signal_hits_on_fall():
    outcome = evaluate_run(_run(-0.3), CLOSES)
    assert outcome["hits"]["30"] is True
    assert outcome["hits"]["1"] is False


def test_neutral_signal_not_directional():
    outcome = evaluate_run(_run(0.01), CLOSES)
    assert outcome["hits"]["1"] is None
    assert outcome["hits"]["30"] is None


def test_aggregate_hit_rate_and_averages():
    runs = [_run(0.4), _run(-0.3), _run(0.0)]
    outcomes = [evaluate_run(run, CLOSES) for run in runs]
    stats = aggregate(outcomes)["30"]
    assert stats["evaluated"] == 3
    assert stats["directional"] == 2
    assert stats["hits"] == 1
    assert stats["hit_rate"] == 0.5
    assert stats["avg_return_positive_signals_pct"] == -10.0
    assert stats["avg_return_negative_signals_pct"] == -10.0
    assert stats["avg_return_neutral_signals_pct"] == -10.0


def test_close_falls_forward_when_date_missing():
    closes = {date(2026, 1, 12): 42.0}
    assert close_for_date(closes, date(2026, 1, 10)) == 42.0
    assert close_for_date(closes, date(2026, 1, 20)) is None


def test_missing_price_yields_none():
    outcome = evaluate_run(_run(0.5, price=None), CLOSES)
    assert outcome["returns_pct"]["1"] is None
    assert outcome["hits"]["1"] is None


async def test_compute_accuracy_end_to_end_with_fake_providers():
    """Sahte fiyat serisiyle compute_accuracy akisi (sayfalama + eslestirme)."""
    from datetime import datetime, timezone

    from crypto_deep_research.deep_research.accuracy import compute_accuracy
    from crypto_deep_research.models import Kline

    base = datetime(2026, 1, 10, tzinfo=timezone.utc)
    klines = [
        Kline(ts=datetime(2026, 1, 10, tzinfo=timezone.utc), open=100, high=101, low=99, close=100, volume=1),
        Kline(ts=datetime(2026, 1, 11, tzinfo=timezone.utc), open=101, high=106, low=100, close=105, volume=1),
        Kline(ts=datetime(2026, 1, 17, tzinfo=timezone.utc), open=108, high=111, low=107, close=110, volume=1),
    ]

    class FakeExchange:
        async def klines_range(self, symbol, interval, *, start_ms, end_ms):
            return [k for k in klines if start_ms <= k.ts.timestamp() * 1000 <= end_ms]

    class FakeProviders:
        exchange = FakeExchange()

    class FakeDb:
        def run_summaries(self, coin=None, limit=100):
            return [
                {
                    "run_id": "r1",
                    "coin": "bitcoin",
                    "symbol": "BTC",
                    "created_at": base.timestamp(),
                    "timeframe": "1d",
                    "weighted_score": 0.4,
                    "up_probability": 64.0,
                    "down_probability": 36.0,
                    "current_price": 100.0,
                }
            ]

    report = await compute_accuracy(FakeProviders(), FakeDb(), coin="bitcoin")
    assert len(report["runs"]) == 1
    outcome = report["runs"][0]
    assert outcome["returns_pct"]["1"] == 5.0
    assert outcome["returns_pct"]["7"] == 10.0
    assert outcome["hits"]["1"] is True
    assert report["horizons"]["1"]["directional"] == 1
    assert report["horizons"]["1"]["hit_rate"] == 1.0
