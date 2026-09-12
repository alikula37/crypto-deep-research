"""Isabet (backtest) analizi: gecmis kosulari sonraki fiyat getirileriyle karsilastirir."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

HORIZONS: tuple[int, ...] = (1, 7, 30)
DIRECTIONAL_THRESHOLD = 0.05
MAX_FORWARD_GAP_DAYS = 4


def _date_key(ts: float) -> date:
    return datetime.fromtimestamp(ts, tz=timezone.utc).date()


def close_for_date(closes: dict[date, float], target: date, max_gap: int = MAX_FORWARD_GAP_DAYS) -> float | None:
    """Hedef tarihteki kapanis; yoksa (tatil/hafta sonu) en yakin ileri tarihi dener."""
    for offset in range(max_gap + 1):
        value = closes.get(target + timedelta(days=offset))
        if value is not None:
            return value
    return None


def evaluate_run(
    run: dict[str, Any], closes: dict[date, float], horizons: tuple[int, ...] = HORIZONS
) -> dict[str, Any]:
    """Bir kosunun vade bazli getirilerini ve yon isabetini hesaplar."""
    entry = run.get("current_price")
    score = run.get("weighted_score")
    run_date = _date_key(run["created_at"])
    returns: dict[str, float | None] = {}
    hits: dict[str, bool | None] = {}
    for horizon in horizons:
        key = str(horizon)
        exit_price = close_for_date(closes, run_date + timedelta(days=horizon))
        value = None
        if entry and exit_price and entry > 0:
            value = round((exit_price / entry - 1) * 100, 3)
        returns[key] = value
        if value is None or score is None or abs(score) < DIRECTIONAL_THRESHOLD:
            hits[key] = None
        else:
            hits[key] = (score > 0 and value > 0) or (score < 0 and value < 0)
    outcome = dict(run)
    outcome["returns_pct"] = returns
    outcome["hits"] = hits
    return outcome


def aggregate(outcomes: list[dict[str, Any]], horizons: tuple[int, ...] = HORIZONS) -> dict[str, Any]:
    """Vade bazinda isabet ve getiri istatistikleri."""
    stats: dict[str, Any] = {}
    for horizon in horizons:
        key = str(horizon)
        evaluated = [o for o in outcomes if o["returns_pct"].get(key) is not None]
        directional = [o for o in evaluated if o["hits"].get(key) is not None]
        hits = [o for o in directional if o["hits"][key]]
        positive = [
            o["returns_pct"][key]
            for o in evaluated
            if (o.get("weighted_score") or 0) >= DIRECTIONAL_THRESHOLD
        ]
        negative = [
            o["returns_pct"][key]
            for o in evaluated
            if (o.get("weighted_score") or 0) <= -DIRECTIONAL_THRESHOLD
        ]
        neutral = [
            o["returns_pct"][key]
            for o in evaluated
            if abs(o.get("weighted_score") or 0) < DIRECTIONAL_THRESHOLD
        ]
        stats[key] = {
            "evaluated": len(evaluated),
            "directional": len(directional),
            "hits": len(hits),
            "hit_rate": round(len(hits) / len(directional), 3) if directional else None,
            "avg_return_positive_signals_pct": (
                round(sum(positive) / len(positive), 3) if positive else None
            ),
            "avg_return_negative_signals_pct": (
                round(sum(negative) / len(negative), 3) if negative else None
            ),
            "avg_return_neutral_signals_pct": (
                round(sum(neutral) / len(neutral), 3) if neutral else None
            ),
        }
    return stats


async def fetch_closes(
    providers: Any, symbol: str, start_ms: int, end_ms: int, interval: str = "1d"
) -> dict[date, float]:
    """Binance gunluk kapanislarini tarihe gore toplar (sayfalama ile)."""
    closes: dict[date, float] = {}
    cursor = start_ms
    day_ms = 86_400_000
    for _ in range(6):
        chunk_end = min(cursor + 999 * day_ms, end_ms)
        klines = await providers.exchange.klines_range(
            symbol, interval, start_ms=cursor, end_ms=chunk_end
        )
        if not klines:
            break
        for kline in klines:
            closes[kline.ts.date()] = kline.close
        if len(klines) < 1000 or chunk_end >= end_ms:
            break
        cursor = int(klines[-1].ts.timestamp() * 1000) + day_ms
    return closes


async def compute_accuracy(
    providers: Any, db: Any, coin: str | None = None, horizons: tuple[int, ...] = HORIZONS
) -> dict[str, Any]:
    """Kosu gecmisini fiyat verisiyle eslestirip isabet panosu uretir."""
    rows = db.run_summaries(coin=coin, limit=200)
    generated_at = datetime.now(timezone.utc).isoformat()
    note = (
        "Getiriler kosu anindaki fiyattan, vade sonundaki gunluk kapanisa gore hesaplanir; "
        "yalnizca |skor| >= 0,05 olan kosular yon tahmini sayilir."
    )
    if not rows:
        return {
            "coin": coin,
            "generated_at": generated_at,
            "horizons": aggregate([], horizons),
            "runs": [],
            "note": note,
        }
    by_coin: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_coin.setdefault(row["coin"], []).append(row)
    outcomes: list[dict[str, Any]] = []
    for coin_id, runs in by_coin.items():
        symbol = runs[0].get("symbol") or coin_id.upper()
        start = min(r["created_at"] for r in runs) - 2 * 86_400
        end = max(r["created_at"] for r in runs) + (max(horizons) + 5) * 86_400
        try:
            closes = await fetch_closes(providers, symbol, int(start * 1000), int(end * 1000))
        except Exception:
            closes = {}
        for run in runs:
            outcomes.append(evaluate_run(run, closes, horizons))
    outcomes.sort(key=lambda item: item["created_at"], reverse=True)
    return {
        "coin": coin,
        "generated_at": generated_at,
        "horizons": aggregate(outcomes, horizons),
        "runs": outcomes,
        "note": note,
    }
