"""Tarihsel seri paketi: funding, basis, makro, Fear&Greed, stablecoin.

Tum seriler gun bazli sozluklerdir ({ISO tarih: deger}) ve yalnizca ilgili gune
kadar olan degerler kullanilir (nokta-zamaninda, sizintisiz).
"""

from __future__ import annotations

import logging
import statistics
from datetime import date, datetime, timedelta, timezone

logger = logging.getLogger(__name__)

EXTENDED_ITEM_IDS: dict[str, int] = {
    "funding_level": 101,
    "funding_z7": 102,
    "funding_cum7": 103,
    "basis_pct": 104,
    "dxy_7d": 105,
    "gold_7d": 106,
    "spx_7d": 107,
    "us10y": 108,
    "vix": 109,
    "vix_7d": 110,
    "fng": 111,
    "fng_7d": 112,
    "stable_7d": 113,
    "stable_30d": 114,
}

EXTENDED_FEATURE_NAMES = [f"x_{name}" for name in EXTENDED_ITEM_IDS]
EXTENDED_CATEGORY = "extended"


def asof(series: dict[str, float], day_iso: str, max_back: int = 5) -> float | None:
    """Bir gunun degerini (yoksa en fazla max_back gun geriye giderek) dondurur."""
    if not series:
        return None
    if day_iso in series:
        return series[day_iso]
    try:
        day = date.fromisoformat(day_iso)
    except ValueError:
        return None
    for offset in range(1, max_back + 1):
        candidate = (day - timedelta(days=offset)).isoformat()
        if candidate in series:
            return series[candidate]
    return None


def change_pct(series: dict[str, float], day_iso: str, lookback_days: int) -> float | None:
    current = asof(series, day_iso)
    if current is None:
        return None
    try:
        past_day = (date.fromisoformat(day_iso) - timedelta(days=lookback_days)).isoformat()
    except ValueError:
        return None
    past = asof(series, past_day, max_back=7)
    if not past:
        return None
    return round((current / past - 1) * 100, 4)


def series_window(series: dict[str, float], day_iso: str, days: int) -> list[float]:
    try:
        end = date.fromisoformat(day_iso)
    except ValueError:
        return []
    start = (end - timedelta(days=days)).isoformat()
    return [value for key, value in sorted(series.items()) if start <= key <= day_iso]


async def load_bundle(providers, symbol: str, *, days: int = 760) -> dict[str, dict[str, float]]:
    """Tum genisletilmis serileri tek seferde yukler (bellekte tutulur)."""
    bundle: dict[str, dict[str, float]] = {}

    try:
        funding = await providers.exchange.funding_history(symbol, days=days + 40)
        daily: dict[str, list[float]] = {}
        for timestamp, rate in funding:
            day = datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc).date().isoformat()
            daily.setdefault(day, []).append(rate)
        bundle["funding"] = {day: sum(values) / len(values) for day, values in daily.items()}
    except Exception:
        logger.info("Funding gecmisi alinamadi: %s", symbol)
        bundle["funding"] = {}

    try:
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        start_ms = now_ms - (days + 40) * 86_400_000
        perp = await providers.exchange.perp_klines_range(
            symbol, "1d", start_ms=start_ms, end_ms=now_ms
        )
        bundle["perp_close"] = {kline.ts.date().isoformat(): kline.close for kline in perp}
    except Exception:
        bundle["perp_close"] = {}

    try:
        macro = await providers.macro.history(period="2y")
        for label in ("DXY", "GOLD", "SPX", "US10Y", "VIX"):
            bundle[f"macro_{label}"] = macro.get(label, {}) or {}
    except Exception:
        logger.info("Makro gecmisi alinamadi")

    try:
        fear_greed = await providers.sentiment.fear_greed(limit=0)
        bundle["fng"] = {
            item.timestamp.date().isoformat(): float(item.value)
            for item in fear_greed
            if getattr(item, "timestamp", None) is not None
        }
    except Exception:
        bundle["fng"] = {}

    try:
        charts = await providers.defillama.stablecoin_charts_all()
        stable: dict[str, float] = {}
        for point in charts:
            timestamp = point.get("date")
            total = point.get("totalCirculatingUSD")
            if timestamp is None or total is None:
                continue
            value = sum(float(v) for v in total.values()) if isinstance(total, dict) else float(total)
            stable[datetime.fromtimestamp(int(timestamp), tz=timezone.utc).date().isoformat()] = value
        bundle["stablecoin_total"] = stable
    except Exception:
        bundle["stablecoin_total"] = {}

    return bundle


def extended_features_for_day(
    bundle: dict[str, dict[str, float]], spot_close: float | None, day_iso: str
) -> dict[int, float]:
    """Bir gun icin genisletilmis ozellikleri (pseudo-madde id -> deger) uretir."""
    funding_series = bundle.get("funding", {})
    funding = asof(funding_series, day_iso)
    funding_window = series_window(funding_series, day_iso, 30)
    funding_z = None
    if funding is not None and len(funding_window) >= 10:
        mean = statistics.mean(funding_window)
        deviation = statistics.pstdev(funding_window)
        funding_z = round((funding - mean) / deviation, 4) if deviation > 0 else 0.0
    funding_cum7 = None
    if funding_series:
        week = series_window(funding_series, day_iso, 7)
        if week:
            funding_cum7 = round(sum(week) * 100, 4)

    perp = asof(bundle.get("perp_close", {}), day_iso)
    basis = None
    if perp and spot_close:
        basis = round((perp / spot_close - 1) * 100, 4)

    fng = asof(bundle.get("fng", {}), day_iso)
    fng_change = change_pct(bundle.get("fng", {}), day_iso, 7)

    values: dict[int, float] = {}
    mapping = {
        "funding_level": (funding * 100 if funding is not None else None),
        "funding_z7": funding_z,
        "funding_cum7": funding_cum7,
        "basis_pct": basis,
        "dxy_7d": change_pct(bundle.get("macro_DXY", {}), day_iso, 7),
        "gold_7d": change_pct(bundle.get("macro_GOLD", {}), day_iso, 7),
        "spx_7d": change_pct(bundle.get("macro_SPX", {}), day_iso, 7),
        "us10y": asof(bundle.get("macro_US10Y", {}), day_iso),
        "vix": asof(bundle.get("macro_VIX", {}), day_iso),
        "vix_7d": change_pct(bundle.get("macro_VIX", {}), day_iso, 7),
        "fng": fng,
        "fng_7d": fng_change,
        "stable_7d": change_pct(bundle.get("stablecoin_total", {}), day_iso, 7),
        "stable_30d": change_pct(bundle.get("stablecoin_total", {}), day_iso, 30),
    }
    for name, value in mapping.items():
        if value is None:
            continue
        item_id = EXTENDED_ITEM_IDS[name]
        values[item_id] = round(float(value), 4)
    return values
