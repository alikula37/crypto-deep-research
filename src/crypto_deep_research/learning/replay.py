"""Tarihsel replay: fiyat turevli maddeleri gecmis gunler icin yeniden hesaplar.

Kapsam (backfill_v1): 1, 7, 14, 15, 16, 18, 19, 21, 24, 35, 36, 37, 48.
Her tarih kesimi yalnizca o gune kadarki OHLCV'yi gorur (sizinti yok); ayni
indicator fonksiyonlari ve ayni agirlikli skorlama kullanilir.

Haber/sosyal turevli maddeler nokta-zamaninda yeniden kurulamaz; canli kosulara
birakilir ve kayitlarda source='backfill' etiketiyle ayrilir.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any

import numpy as np

from crypto_deep_research.analysis.base import clamp
from crypto_deep_research.analysis.indicators import (
    atr,
    candle_patterns,
    compute_levels,
    detect_chart_patterns,
    indicator_score,
    indicator_snapshot,
    to_dataframe,
)
from crypto_deep_research.deep_research.engine import (
    compute_group_factors,
    compute_weighted_score,
    expected_range,
    probabilities,
)
from crypto_deep_research.deep_research.registry import load_registry
from crypto_deep_research.models import ItemResult, Kline
from crypto_deep_research.providers.base import ProviderError

logger = logging.getLogger(__name__)

BACKFILL_ITEM_IDS = (1, 7, 14, 15, 16, 18, 19, 21, 24, 35, 36, 37, 48)
MIN_HISTORY = 220
CONFIDENCE = 0.7
HORIZONS = (1, 7, 30)
BATCH_SIZE = 100
DAY_MS = 86_400_000


def _pattern_score(patterns: list[str]) -> float:
    score = 0.0
    for pattern in patterns:
        lower = pattern.lower()
        if any(word in lower for word in ("bullish", "dip", "yükseliş", "kırılımı (breakout)", "double bottom")):
            score += 0.15
        if any(word in lower for word in ("bearish", "tepe", "düşüş", "breakdown", "double top")):
            score -= 0.15
    return float(np.clip(score, -1.0, 1.0))


def _hurst(log_returns: np.ndarray) -> float | None:
    if len(log_returns) < 64:
        return None
    lags = [2, 4, 8, 16, 32]
    variances = []
    for lag in lags:
        aggregated = np.add.reduceat(log_returns, np.arange(0, len(log_returns) - lag, lag))
        variances.append(max(float(np.var(aggregated)), 1e-12))
    beta = float(np.polyfit(np.log(lags), np.log(variances), 1)[0])
    return beta / 2.0


def _psych_score(price: float) -> float:
    import math

    magnitude = 10 ** math.floor(math.log10(price)) if price > 0 else 1
    levels = sorted(
        {
            round(price / (magnitude * factor / 10)) * (magnitude * factor / 10)
            for factor in (0.5, 1, 2, 5, 10)
        }
    )
    levels = [level for level in levels if level > 0]
    above = [level for level in levels if level >= price]
    below = [level for level in levels if level < price]
    distance_resistance = (min(above) / price - 1) * 100 if above else None
    distance_support = (price / max(below) - 1) * 100 if below else None
    if distance_resistance is not None and distance_resistance < 0.5:
        return -0.15
    if distance_support is not None and distance_support < 0.5:
        return 0.15
    if distance_resistance is not None and distance_resistance > 2:
        return 0.05
    return 0.0


def _similarity_score(closes: np.ndarray, returns: np.ndarray) -> float:
    window, horizon = 20, 10
    if len(returns) < window + horizon + 20:
        return 0.0
    current = returns[-window:]
    candidates: list[tuple[float, float]] = []
    for end in range(window, len(returns) - horizon - window):
        past = returns[end - window : end]
        distance = float(np.linalg.norm(past - current))
        forward = float(closes[end + horizon] / closes[end] - 1) * 100
        candidates.append((distance, forward))
    candidates.sort(key=lambda item: item[0])
    top = candidates[: min(8, len(candidates))]
    if not top:
        return 0.0
    forwards = [item[1] for item in top]
    average = float(np.mean(forwards))
    positive = sum(1 for value in forwards if value > 0) / len(forwards)
    return clamp(average / 6.0) * 0.7 + (positive - 0.5) * 0.6


def compute_component_scores(df) -> dict[str, Any]:
    """Bir tarih kesimi icin madde skorlarini uretir (yalnizca kesim verisiyle)."""
    snapshot = indicator_snapshot(df)
    price = float(snapshot["price"])
    levels = compute_levels(df, price)
    indicator, _, _ = indicator_score(snapshot)
    candles = candle_patterns(df)
    chart = detect_chart_patterns(df)
    candle_score = _pattern_score(candles)
    chart_score = _pattern_score(chart)
    technical = float(np.clip(indicator * 0.8 + (candle_score + chart_score) * 0.5, -1.0, 1.0))

    fib = (levels.get("fibonacci") or {})
    fib_score = 0.0
    mid = fib.get("0.5")
    if mid:
        fib_score = 0.1 if price > float(mid) else -0.1

    resistance_distance = levels.get("distance_to_resistance_pct")
    support_distance = levels.get("distance_to_support_pct")
    level_score = 0.0
    if resistance_distance is not None and resistance_distance < 1.5:
        level_score -= 0.15
    if support_distance is not None and support_distance < 1.5:
        level_score += 0.15

    volume_ratio = None
    if len(df) >= 21:
        volume_ma = float(df["volume"].tail(20).mean())
        if volume_ma > 0:
            volume_ratio = float(df["volume"].iloc[-1] / volume_ma)
    volume_score = 0.0
    if volume_ratio is not None:
        volume_score = 0.15 if volume_ratio > 1.3 else (-0.1 if volume_ratio < 0.6 else 0.0)

    closes = df["close"].values.astype(float)
    log_returns = np.diff(np.log(closes))
    hurst = _hurst(log_returns)
    trend_30d = float(closes[-1] / closes[-31] - 1) * 100 if len(closes) > 31 else 0.0
    if hurst is None:
        fractal_score, regime = 0.0, None
    elif hurst > 0.58:
        fractal_score, regime = clamp(trend_30d / 20.0) * 0.7, "trend rejimi (persistent)"
    elif hurst < 0.42:
        fractal_score, regime = -clamp(trend_30d / 20.0) * 0.5, "ortalamaya dönüş rejimi"
    else:
        fractal_score, regime = 0.0, "rastgele yuruyus"

    vol_score = 0.0
    percentile = None
    if len(log_returns) > 60:
        lam = 0.94
        ewma_var = float(np.var(log_returns))
        for value in log_returns:
            ewma_var = lam * ewma_var + (1 - lam) * value * value
        current_vol = float(np.sqrt(ewma_var)) * 100
        rolling = [
            float(np.std(log_returns[index - 30 : index])) * 100 for index in range(30, len(log_returns))
        ]
        if rolling:
            percentile = sum(1 for value in rolling if value <= current_vol) / len(rolling)
            if percentile > 0.9:
                vol_score = 0.15

    atr_series = atr(df)
    atr_pct = float(atr_series.iloc[-1] / price * 100) if len(df) >= 15 else None

    trend_score = 0.0
    if len(log_returns) >= 60:
        recent = log_returns[-90:]
        mean_daily = float(np.mean(recent))
        std_daily = float(np.std(recent, ddof=1))
        if std_daily > 0:
            t_stat = mean_daily / std_daily * float(np.sqrt(len(recent)))
            trend_score = float(np.clip(t_stat / 3.5, -1, 1)) * 0.8

    season_score = 0.0
    if len(log_returns) >= 200:
        months = df.index[1:]
        current_month = df.index[-1].month
        same_month = [float(log_returns[i]) for i in range(len(log_returns)) if months[i].month == current_month]
        if same_month:
            season_score = clamp(float(np.mean(same_month)) * 100 / 10.0) * 0.4

    similarity_score = _similarity_score(closes, log_returns)
    psych_score = _psych_score(price)

    volatility_bucket = None
    if percentile is not None:
        volatility_bucket = "low" if percentile < 0.33 else ("high" if percentile > 0.66 else "mid")

    return {
        "price": price,
        "atr_pct": atr_pct,
        "regime": regime,
        "volatility_bucket": volatility_bucket,
        "volume_ratio": volume_ratio,
        "scores": {
            1: technical,
            7: float(clamp(indicator)),
            14: candle_score,
            15: chart_score,
            16: float(clamp(fib_score)),
            18: volume_score,
            19: float(clamp(level_score)),
            21: fractal_score,
            24: float(clamp(similarity_score)),
            35: vol_score,
            36: float(clamp(season_score)),
            37: float(clamp(trend_score)),
            48: psych_score,
        },
    }


def _build_sample(
    coin_id: str,
    symbol: str,
    timestamp: float,
    components: dict[str, Any],
    closes: np.ndarray,
    index: int,
    specs: list,
    factors: dict[int, float],
    extended: dict[int, float] | None = None,
) -> dict[str, Any] | None:
    scores = components["scores"]
    items: list[ItemResult] = []
    for spec in specs:
        if spec.id not in scores:
            continue
        items.append(
            ItemResult(
                item_id=spec.id,
                title_tr=spec.title_tr,
                category=spec.category,
                weight=spec.weight,
                key=f"item_{spec.id}",
                title=spec.title_tr,
                status="ok",
                score=round(float(scores[spec.id]), 4),
                confidence=CONFIDENCE,
            )
        )
    weighted = compute_weighted_score(items, group_factors=factors)
    if weighted is None:
        return None
    up, down = probabilities(weighted)
    low, high = expected_range(components["price"], components["atr_pct"], weighted)
    run_id = f"bf_{coin_id}_{int(timestamp)}"
    active = [item for item in items if item.score is not None and item.confidence > 0]
    strong = [item for item in active if abs(item.score) >= 0.05]
    strong_weight = sum(item.weight * item.confidence for item in strong)
    signal_strength = (
        round(sum(item.score * item.weight * item.confidence for item in strong) / strong_weight, 4)
        if strong_weight
        else 0.0
    )
    values = [item.score for item in active]
    mean = sum(values) / len(values) if values else None
    dispersion = (
        (sum((value - mean) ** 2 for value in values) / len(values)) ** 0.5 if values and mean is not None else None
    )
    category_scores: dict[str, float] = {}
    category_weight: dict[str, float] = {}
    for item in active:
        category_scores[item.category] = category_scores.get(item.category, 0.0) + item.score * item.weight
        category_weight[item.category] = category_weight.get(item.category, 0.0) + item.weight
    category_scores = {
        key: round(value / category_weight[key], 4) for key, value in category_scores.items() if category_weight[key]
    }
    registry_weight = sum(spec.weight for spec in specs) or 1.0
    total_weight = sum(item.weight * item.confidence for item in active)
    items_hash = hashlib.sha256(
        "|".join(f"{item.item_id}:{item.score}" for item in items).encode()
    ).hexdigest()[:16]
    features = {
        "run_id": run_id,
        "coin": coin_id,
        "created_at": timestamp,
        "profile": "backfill",
        "n_ok": len(items),
        "n_partial": 0,
        "n_no_data": max(len(specs) - len(items), 0),
        "n_error": 0,
        "coverage_ratio": round(len(items) / max(len(specs), 1), 4),
        "coverage_weighted": round(total_weight / registry_weight, 4),
        "weighted_score": weighted,
        "signal_strength": signal_strength,
        "score_mean": round(mean, 4) if mean is not None else None,
        "score_dispersion": round(dispersion, 4) if dispersion is not None else None,
        "confidence_mean": CONFIDENCE,
        "category_scores": __import__("json").dumps(category_scores, ensure_ascii=False),
        "atr_pct": components["atr_pct"],
        "regime": components["regime"],
        "volatility_bucket": components["volatility_bucket"],
        "current_price": components["price"],
        "up_probability": up,
        "down_probability": down,
        "expected_low": low,
        "expected_high": high,
        "items_hash": items_hash,
    }
    item_rows = [
        (
            run_id, item.item_id, coin_id, item.category,
            f"backfill:{item.item_id}", item.weight, item.score, item.confidence,
            "ok", round(item.score * item.weight * item.confidence * factors.get(item.item_id, 1.0), 6),
        )
        for item in items
    ]
    for pseudo_id, value in (extended or {}).items():
        # Genisletilmis ozellikler skorlamaya girmez (weight 0); yalnizca ML ozelligi.
        item_rows.append(
            (run_id, pseudo_id, coin_id, "extended", "backfill:extended", 0.0, float(value), 1.0, "ok", None)
        )
    direction = "up" if weighted >= 0.05 else ("down" if weighted <= -0.05 else "neutral")
    entry_price = float(closes[index])
    entry_dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    outcome_rows = []
    for horizon in HORIZONS:
        exit_index = index + horizon
        if exit_index >= len(closes):
            continue
        exit_price = float(closes[exit_index])
        return_pct = round((exit_price / entry_price - 1) * 100, 4)
        hit = None
        if direction == "up":
            hit = 1 if return_pct > 0 else 0
        elif direction == "down":
            hit = 1 if return_pct < 0 else 0
        target = (entry_dt.date() + __import__("datetime").timedelta(days=horizon)).isoformat()
        outcome_rows.append(
            (
                run_id, horizon, coin_id, symbol, entry_price, timestamp, target,
                timestamp + horizon * 86400, exit_price, return_pct, hit, direction,
                weighted, timestamp + horizon * 86400,
            )
        )
    if not outcome_rows:
        return None
    features["outcomes"] = outcome_rows
    features["items"] = item_rows
    return features


async def fetch_history(providers, symbol: str, days: int) -> list[Kline]:
    """Binance gunluk kapanislari; gosterge isinma payiyla birlikte."""
    now = int(datetime.now(timezone.utc).timestamp() * 1000)
    start = now - (days + MIN_HISTORY + 40) * DAY_MS
    klines: list[Kline] = []
    cursor = start
    for _ in range(4):
        chunk = await providers.exchange.klines_range(
            symbol, "1d", start_ms=cursor, end_ms=now
        )
        if not chunk:
            break
        klines.extend(chunk)
        if len(chunk) < 1000:
            break
        cursor = int(chunk[-1].ts.timestamp() * 1000) + DAY_MS
    return klines


async def replay_coin(
    providers,
    db,
    coin_id: str,
    symbol: str,
    *,
    days: int = 730,
    extended: bool = True,
) -> dict[str, Any]:
    """Bir coin icin gunluk tarihsel ornekler uretir ve kaydeder."""
    try:
        klines = await fetch_history(providers, symbol, days)
    except ProviderError:
        klines = []
    if len(klines) < MIN_HISTORY + max(HORIZONS) + 5:
        return {"coin": coin_id, "samples": 0, "reason": "yetersiz gecmis"}

    df = to_dataframe(klines)
    if len(df) < MIN_HISTORY + max(HORIZONS) + 5:
        return {"coin": coin_id, "samples": 0, "reason": "veri kisa"}

    specs = load_registry()
    factors = compute_group_factors(specs)
    closes = df["close"].values.astype(float)
    timestamps = [int(ts.timestamp()) for ts in df.index]
    days_iso = [ts.date().isoformat() for ts in df.index]
    bundle: dict[str, dict[str, float]] = {}
    if extended:
        from crypto_deep_research.learning.history import load_bundle

        bundle = await load_bundle(providers, symbol, days=days)

    db.execute("DELETE FROM feature_snapshots WHERE run_id LIKE ?", (f"bf_{coin_id}_%",))
    db.execute("DELETE FROM outcomes WHERE run_id LIKE ?", (f"bf_{coin_id}_%",))

    samples: list[dict[str, Any]] = []
    written = 0
    for index in range(MIN_HISTORY, len(df) - max(HORIZONS)):
        slice_df = df.iloc[: index + 1]
        components = compute_component_scores(slice_df)
        extended_values = None
        if bundle:
            from crypto_deep_research.learning.history import extended_features_for_day

            extended_values = extended_features_for_day(
                bundle, components["price"], days_iso[index]
            )
        sample = _build_sample(
            coin_id, symbol, timestamps[index], components, closes, index, specs, factors,
            extended=extended_values,
        )
        if sample is None:
            continue
        samples.append(sample)
        if len(samples) >= BATCH_SIZE:
            written += db.save_backfill_batch(samples)
            samples = []
    if samples:
        written += db.save_backfill_batch(samples)
    return {"coin": coin_id, "samples": written, "history_days": len(df), "extended": bool(bundle)}
