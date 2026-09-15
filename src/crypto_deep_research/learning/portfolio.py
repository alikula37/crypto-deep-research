"""Kesitsel portfoy backtest'i: model siralamasiyla en iyi k coini secer.

Yalnizca walk-forward OOS tahminleri kullanilir (predictions.is_oos=1); boylece
ileriye bakma sizintisi olmaz. N gunluk yeniden dengeleme ile ust-k ve alt-k
sepetleri, esit agirlikli evren ve BTC al-tut ile karsilastirilir; maliyet dusulur.
"""

from __future__ import annotations

import logging
import math
import statistics
from datetime import date, datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


def _load_rows(db, horizon: int, source: str | None) -> list[dict[str, Any]]:
    conditions = [
        "p.is_oos = 1",
        "p.horizon_days = ?",
        "o.status = 'filled'",
        "o.return_pct IS NOT NULL",
    ]
    params: list[Any] = [horizon]
    if source:
        conditions.append("COALESCE(f.source, 'live') = ?")
        params.append(source)
    return db.query(
        f"""
        SELECT p.run_id, p.probability_up, o.coin, o.entry_at, o.target_date, o.return_pct
        FROM predictions p
        JOIN outcomes o ON o.run_id = p.run_id AND o.horizon_days = p.horizon_days
        JOIN feature_snapshots f ON f.run_id = o.run_id
        WHERE {' AND '.join(conditions)}
        """,
        tuple(params),
    )


def select_rebalance_dates(days: list[str], rebalance_days: int) -> list[str]:
    chosen: list[str] = []
    previous: date | None = None
    for day in sorted(days):
        current = date.fromisoformat(day)
        if previous is None or (current - previous).days >= rebalance_days:
            chosen.append(day)
            previous = current
    return chosen


def _sharpe(values: list[float], periods_per_year: float) -> float | None:
    if len(values) < 3:
        return None
    mean = statistics.mean(values)
    deviation = statistics.pstdev(values)
    if deviation <= 0:
        return None
    return round(mean / deviation * math.sqrt(periods_per_year), 3)


def run_backtest(
    db,
    *,
    horizon: int = 30,
    top_k: int = 3,
    cost_bps: float = 10.0,
    rebalance_days: int = 30,
    source: str | None = "backfill",
) -> dict[str, Any]:
    """Kesitsel portfoy backtest'i calistirir; OOS tahmin sart."""
    rows = _load_rows(db, horizon, source)
    if not rows:
        return {"status": "no_data", "reason": "OOS tahmini yok (once ml-train calistirin)."}

    by_day: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        day = datetime.fromtimestamp(row["entry_at"], tz=timezone.utc).date().isoformat()
        by_day.setdefault(day, []).append(row)
    required = max(top_k * 2, 4)
    by_day = {day: items for day, items in by_day.items() if len(items) >= required}
    if len(by_day) < 4:
        return {"status": "no_data", "reason": "Yeterli kesitsel gun yok."}

    rebalance_dates = select_rebalance_dates(list(by_day), rebalance_days)
    pairs = list(zip(rebalance_dates, rebalance_dates[1:], strict=False))
    if len(pairs) < 3:
        return {"status": "no_data", "reason": "Yeniden dengeleme donemi yetersiz."}

    equity_top = equity_long_short = equity_equal = equity_btc = 1.0
    top_returns: list[float] = []
    ls_returns: list[float] = []
    spreads: list[float] = []
    btc_returns: list[float] = []
    equal_returns: list[float] = []
    previous_members: set[str] = set()

    for start_day, _end_day in pairs:
        entries = sorted(by_day[start_day], key=lambda row: -(row["probability_up"] or 0))
        top = entries[:top_k]
        bottom = entries[-top_k:]
        top_return = statistics.mean(row["return_pct"] for row in top) / 100
        bottom_return = statistics.mean(row["return_pct"] for row in bottom) / 100
        equal_return = statistics.mean(row["return_pct"] for row in entries) / 100
        btc_row = next((row for row in entries if row["coin"] == "bitcoin"), None)
        btc_return = (btc_row["return_pct"] / 100) if btc_row else 0.0

        members = {row["coin"] for row in top}
        turnover = (
            len(members.symmetric_difference(previous_members)) / max(len(members), 1)
            if previous_members
            else 1.0
        )
        cost = turnover * cost_bps / 10_000 * 2

        net_top = top_return - cost
        equity_top *= 1 + net_top
        ls_return = (top_return - bottom_return) / 2 - cost
        equity_long_short *= 1 + ls_return
        equity_equal *= 1 + equal_return
        equity_btc *= 1 + btc_return

        top_returns.append(net_top)
        ls_returns.append(ls_return)
        spreads.append(top_return - bottom_return)
        btc_returns.append(btc_return)
        equal_returns.append(equal_return)
        previous_members = members

    periods_per_year = 365 / max(rebalance_days, 1)
    hit_rate = sum(1 for spread in spreads if spread > 0) / len(spreads)
    return {
        "status": "ok",
        "horizon": horizon,
        "top_k": top_k,
        "rebalance_days": rebalance_days,
        "cost_bps": cost_bps,
        "periods": len(top_returns),
        "equity": {
            "top_k": round(equity_top, 4),
            "long_short": round(equity_long_short, 4),
            "equal_weight": round(equity_equal, 4),
            "btc": round(equity_btc, 4),
        },
        "net_sharpe": {
            "top_k": _sharpe(top_returns, periods_per_year),
            "long_short": _sharpe(ls_returns, periods_per_year),
            "equal_weight": _sharpe(equal_returns, periods_per_year),
            "btc": _sharpe(btc_returns, periods_per_year),
        },
        "avg_top_k_return_pct": round(statistics.mean(top_returns) * 100, 2),
        "avg_spread_pct": round(statistics.mean(spreads) * 100, 2),
        "hit_rate": round(hit_rate, 3),
    }
