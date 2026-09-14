"""Kesitsel ozellikler: bir coinin ayni gun diger coinlere gore konumu.

Girdi olarak backfill (veya canli) ozellik anlik goruntulerindeki gunluk fiyatlari
kullanir; BTC/ETH'e gore goreli guc, evren sirasi, piyasa genisligi ve alt sezonu
gibi sinyaller uretir. Cikti pseudo-madde (id 121-130) olarak saklanir.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import numpy as np

from crypto_deep_research.learning.history import CROSS_ITEM_IDS, asof, change_pct

logger = logging.getLogger(__name__)

BENCHMARKS = ("bitcoin", "ethereum")


def percentile_rank(values: list[float], value: float) -> float | None:
    usable = [item for item in values if item is not None]
    if not usable:
        return None
    below = sum(1 for item in usable if item < value)
    return round(below / max(len(usable) - 1, 1), 4)


def beta_corr(
    coin_prices: dict[str, float],
    btc_prices: dict[str, float],
    day_iso: str,
    window: int = 30,
) -> tuple[float | None, float | None]:
    """BTC'ye karsi 30 gunluk beta ve korelasyon (gun sonuna kadar, sizintisiz)."""
    dates = sorted(day for day in coin_prices if day <= day_iso)[-window - 1 :]
    if len(dates) < max(10, window // 2):
        return None, None
    coin_returns: list[float] = []
    btc_returns: list[float] = []
    for previous, current in zip(dates, dates[1:], strict=False):
        coin_now, coin_prev = coin_prices.get(current), coin_prices.get(previous)
        btc_now = asof(btc_prices, current, max_back=2)
        btc_prev = asof(btc_prices, previous, max_back=2)
        if None in (coin_now, coin_prev, btc_now, btc_prev):
            continue
        if coin_prev == 0 or btc_prev == 0:
            continue
        coin_returns.append(coin_now / coin_prev - 1)
        btc_returns.append(btc_now / btc_prev - 1)
    if len(coin_returns) < 10:
        return None, None
    x = np.asarray(coin_returns, dtype=float)
    y = np.asarray(btc_returns, dtype=float)
    variance = float(np.var(y))
    beta = float(np.cov(x, y)[0][1] / variance) if variance > 0 else None
    corr = float(np.corrcoef(x, y)[0][1]) if len(x) > 2 and np.std(x) > 0 else None
    return (
        round(beta, 4) if beta is not None else None,
        round(corr, 4) if corr is not None else None,
    )


def _snapshot_series(db, source: str) -> tuple[dict[str, dict[str, float]], dict[tuple[str, str], str]]:
    rows = db.query(
        """
        SELECT run_id, coin, created_at, current_price FROM feature_snapshots
        WHERE COALESCE(source, 'live') = ? AND current_price IS NOT NULL
        ORDER BY created_at
        """,
        (source,),
    )
    series: dict[str, dict[str, float]] = {}
    run_by: dict[tuple[str, str], str] = {}
    for row in rows:
        day = datetime.fromtimestamp(row["created_at"], tz=timezone.utc).date().isoformat()
        series.setdefault(row["coin"], {})[day] = float(row["current_price"])
        run_by[(row["coin"], day)] = row["run_id"]
    return series, run_by


def compute_cross_section(db, source: str = "backfill") -> dict[str, Any]:
    """Ayni gun icin tum coinlerin karsilastirmali ozelliklerini uretir ve kaydeder."""
    series, run_by = _snapshot_series(db, source)
    if "bitcoin" not in series or len(series) < 2:
        return {"written": 0, "reason": "yetersiz evren"}

    coins = sorted(series)
    all_days = sorted({day for days in series.values() for day in days})
    returns_cache: dict[tuple[str, str, int], float | None] = {}

    def get_return(coin: str, day: str, lookback: int) -> float | None:
        key = (coin, day, lookback)
        if key not in returns_cache:
            returns_cache[key] = change_pct(series[coin], day, lookback)
        return returns_cache[key]

    rows: list[tuple[str, int, str, str, str, float]] = []
    for day in all_days:
        returns_7 = {coin: get_return(coin, day, 7) for coin in coins if day in series[coin]}
        returns_30 = {coin: get_return(coin, day, 30) for coin in coins if day in series[coin]}
        listed_7 = [value for value in returns_7.values() if value is not None]
        listed_30 = [value for value in returns_30.values() if value is not None]
        btc_7 = returns_7.get("bitcoin")
        btc_30 = returns_30.get("bitcoin")
        eth_30 = returns_30.get("ethereum")
        market_7 = round(float(np.mean(listed_7)), 4) if listed_7 else None
        breadth_30 = (
            round(sum(1 for value in listed_30 if value > 0) / len(listed_30), 4)
            if listed_30
            else None
        )
        alt_values = [
            value for coin, value in returns_30.items() if coin not in BENCHMARKS and value is not None
        ]
        altseason = (
            round(float(np.mean(alt_values)) - btc_30, 4)
            if alt_values and btc_30 is not None
            else None
        )

        for coin in coins:
            run_id = run_by.get((coin, day))
            if run_id is None:
                continue
            values: dict[int, float] = {}
            r7, r30 = returns_7.get(coin), returns_30.get(coin)
            if r7 is not None and btc_7 is not None:
                values[CROSS_ITEM_IDS["xs_rs_btc_7d"]] = round(r7 - btc_7, 4)
            if r30 is not None and btc_30 is not None:
                values[CROSS_ITEM_IDS["xs_rs_btc_30d"]] = round(r30 - btc_30, 4)
            if r30 is not None and eth_30 is not None:
                values[CROSS_ITEM_IDS["xs_rs_eth_30d"]] = round(r30 - eth_30, 4)
            if r7 is not None:
                rank = percentile_rank(listed_7, r7)
                if rank is not None:
                    values[CROSS_ITEM_IDS["xs_rank_7d"]] = rank
            if r30 is not None:
                rank = percentile_rank(listed_30, r30)
                if rank is not None:
                    values[CROSS_ITEM_IDS["xs_rank_30d"]] = rank
            if market_7 is not None:
                values[CROSS_ITEM_IDS["xs_market_7d"]] = market_7
            if breadth_30 is not None:
                values[CROSS_ITEM_IDS["xs_breadth_30d"]] = breadth_30
            if altseason is not None:
                values[CROSS_ITEM_IDS["xs_altseason_30d"]] = altseason
            beta, corr = beta_corr(series[coin], series["bitcoin"], day)
            if beta is not None:
                values[CROSS_ITEM_IDS["xs_beta_btc_30d"]] = beta
            if corr is not None:
                values[CROSS_ITEM_IDS["xs_corr_btc_30d"]] = corr
            for item_id, value in values.items():
                rows.append((run_id, item_id, coin, "cross", f"{source}:cross", float(value)))

    written = db.save_pseudo_features(rows)
    return {"written": written, "coins": len(coins), "days": len(all_days), "source": source}
