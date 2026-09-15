"""Delta-notr fonlama carry: sinyal, paper adim ve durum ozeti.

Strateji: her `rebalance_days` gununde geriye donuk `lookback` gun ortalamasi
pozitif ve en yuksek `top_n` coin secilir; long spot + short perp kurulur.
Getiri = toplanan fonlama - islem maliyeti (fiyat riski delta-notr oldugu icin yok).
Paper takipte pozisyonlar gercek emirle degil, sanal olarak izlenir.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

import pandas as pd

from crypto_deep_research.learning.strategies import carry_frame, select_holdings

logger = logging.getLogger(__name__)

CARRY_DEFAULTS: dict[str, Any] = {
    "universe": 40,
    "top_n": 8,
    "lookback": 7,
    "rebalance_days": 3,
    "cost_bps": 10.0,
    "min_avg": 0.0,
    "max_avg": 0.005,
    "hysteresis": 0.0002,
    "weighting": "equal",
    "max_weight": 0.25,
    "min_volume_usd": 50_000_000,
}


async def fetch_funding_map(
    providers, symbols: list[str], days: int = 30
) -> dict[str, dict[str, float]]:
    """Coin bazli gunluk fonlama toplamlari (8 saatlik oranlarin toplami)."""
    funding: dict[str, dict[str, float]] = {}
    for symbol in symbols:
        try:
            rows = await providers.exchange.funding_history(symbol, days=days)
        except Exception as exc:  # tek sembol hatasi taramayi durdurmasin
            logger.warning("Fonlama alinamadi %s: %s", symbol, exc)
            continue
        daily: dict[str, list[float]] = {}
        for timestamp, rate in rows:
            day = datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc).date().isoformat()
            daily.setdefault(day, []).append(rate)
        if daily:
            funding[symbol] = {day: sum(values) for day, values in daily.items()}
    return funding


def rank_funding(
    funding_map: dict[str, dict[str, float]],
    *,
    top_n: int = 8,
    lookback: int = 7,
    min_avg: float = 0.0,
    max_avg: float | None = None,
    as_of: str | None = None,
    limit: int = 30,
) -> list[dict[str, Any]]:
    """Geriye donuk ortalama fonlamaya gore sirali liste; ust `top_n` secili isaretlenir."""
    if not funding_map:
        return []
    frame = carry_frame(funding_map)
    if as_of:
        frame = frame.loc[: pd.Timestamp(as_of, tz="UTC")]
    if len(frame) < lookback:
        return []
    window = frame.iloc[-lookback:]
    counts = window.notna().sum()
    history = window.mean()
    ranked: list[dict[str, Any]] = []
    for symbol, value in history.sort_values(ascending=False).items():
        if not counts.get(symbol):
            continue
        ranked.append(
            {
                "symbol": str(symbol),
                "avg_funding": round(float(value), 6),
                "days": int(counts.get(symbol, 0)),
                "selected": False,
            }
        )
    selected = 0
    for row in ranked:
        tradeable = row["avg_funding"] > min_avg and (
            max_avg is None or row["avg_funding"] <= max_avg
        )
        if selected < top_n and tradeable:
            row["selected"] = True
            selected += 1
    return ranked[: max(limit, top_n)]


def apply_step(
    state: dict[str, Any] | None,
    funding_map: dict[str, dict[str, float]],
    params: dict[str, Any],
    today: str,
    *,
    ranking: list[dict[str, Any]] | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    """Saf paper adimi: gunluk fonlama gelirini isler, gerekiyorsa yeniden dengeler."""
    if state and state.get("as_of") == today:
        return state
    merged = {**CARRY_DEFAULTS, **params}
    lookback = int(merged["lookback"])
    rebalance_days = int(merged["rebalance_days"])
    cost_bps = float(merged["cost_bps"])
    top_n = int(merged["top_n"])

    ranked = ranking
    if ranked is None:
        ranked = rank_funding(
            funding_map,
            top_n=top_n,
            lookback=lookback,
            min_avg=float(merged.get("min_avg", 0.0)),
            max_avg=merged.get("max_avg"),
            as_of=today,
        )
    frame = carry_frame(funding_map) if funding_map else pd.DataFrame()
    today_date = date.fromisoformat(today)
    prev_day = pd.Timestamp(today_date - timedelta(days=1), tz="UTC")

    def _history() -> dict[str, float]:
        if frame.empty:
            return {}
        window = frame.loc[: pd.Timestamp(today, tz="UTC")].iloc[-lookback:]
        means = window.mean()
        return {
            str(symbol): float(value)
            for symbol, value in means.items()
            if pd.notna(value)
        }

    def _pick(incumbents: set[str]) -> dict[str, float]:
        return select_holdings(
            _history(),
            top_n=top_n,
            min_avg=float(merged.get("min_avg", 0.0)),
            max_avg=merged.get("max_avg"),
            incumbents=incumbents,
            hysteresis=float(merged.get("hysteresis", 0.0)),
            weighting=str(merged.get("weighting", "equal")),
            max_weight=float(merged.get("max_weight", 0.25)),
        )

    if state is None:
        weights = _pick(set())
        history = _history()
        holdings = [
            {
                "symbol": symbol,
                "weight": round(weight, 6),
                "avg_funding": round(history.get(symbol, 0.0), 6),
            }
            for symbol, weight in weights.items()
        ]
        costs = (sum(weights.values()) if weights else 0.0) * cost_bps * 2 / 10_000
        equity = 1.0 - costs
        return {
            "as_of": today,
            "params": {**merged, "top_n": top_n},
            "holdings": holdings,
            "ranking": ranked,
            "equity": equity,
            "daily_return": -costs,
            "funding_income": 0.0,
            "costs": costs,
            "rebalanced": bool(weights),
            "last_rebalance": today if weights else None,
            "note": note or "acilis",
        }

    income = 0.0
    for holding in state.get("holdings", []):
        symbol = holding["symbol"]
        value = None
        if not frame.empty and prev_day in frame.index and symbol in frame.columns:
            value = frame.at[prev_day, symbol]
            if pd.isna(value):
                value = None
        income += float(holding.get("weight", 0.0)) * float(value or 0.0)

    last_rebalance = state.get("last_rebalance") or state.get("as_of")
    costs = 0.0
    holdings = state.get("holdings", [])
    rebalanced = False
    if last_rebalance and (today_date - date.fromisoformat(last_rebalance)).days >= rebalance_days:
        old_weights = {h["symbol"]: float(h.get("weight", 0.0)) for h in state.get("holdings", [])}
        new_weights = _pick(set(old_weights))
        turnover = sum(
            abs(new_weights.get(symbol, 0.0) - old_weights.get(symbol, 0.0))
            for symbol in set(new_weights) | set(old_weights)
        )
        costs = turnover * cost_bps * 2 / 10_000
        history = _history()
        holdings = [
            {
                "symbol": symbol,
                "weight": round(weight, 6),
                "avg_funding": round(history.get(symbol, 0.0), 6),
            }
            for symbol, weight in new_weights.items()
        ]
        rebalanced = True
        last_rebalance = today

    daily_return = income - costs
    equity = float(state.get("equity", 1.0)) * (1 + daily_return)
    return {
        "as_of": today,
        "params": {**merged, "top_n": top_n},
        "holdings": holdings,
        "ranking": ranked,
        "equity": equity,
        "daily_return": daily_return,
        "funding_income": income,
        "costs": costs,
        "rebalanced": rebalanced,
        "last_rebalance": last_rebalance,
        "note": note,
    }


EDGE_WARN_ANNUAL = 0.03
EDGE_CRITICAL_ANNUAL = 0.01


def edge_alert(snapshot: dict[str, Any]) -> dict[str, Any] | None:
    """30 gunluk net carry yilliklandirmasina gore rejim uyarisi."""
    value = snapshot.get("net_30d_annual")
    if value is None:
        value = snapshot.get("edge_30d_annual")
    if value is None:
        return None
    if value < EDGE_CRITICAL_ANNUAL:
        severity = "critical"
    elif value < EDGE_WARN_ANNUAL:
        severity = "warning"
    else:
        return None
    return {
        "severity": severity,
        "net_30d_annual": snapshot.get("net_30d_annual"),
        "edge_30d_annual": snapshot.get("edge_30d_annual"),
        "message": f"Carry edge zayif: 30g net yillik %{value * 100:.1f}"
        f" (uyari <%{EDGE_WARN_ANNUAL * 100:.0f}, kritik <%{EDGE_CRITICAL_ANNUAL * 100:.0f})",
    }


def next_rebalance_date(state: dict[str, Any] | None) -> str | None:
    if not state:
        return None
    params = {**CARRY_DEFAULTS, **(state.get("params") or {})}
    last = state.get("last_rebalance") or state.get("as_of")
    if not last:
        return None
    return (date.fromisoformat(last) + timedelta(days=int(params["rebalance_days"]))).isoformat()


async def paper_step(
    db, providers, params: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Canli veriyle tek paper adimi calistir ve durumu kaydet."""
    merged = {**CARRY_DEFAULTS, **(params or {})}
    state = db.carry_state_latest()
    today = datetime.now(timezone.utc).date().isoformat()
    if state and state.get("as_of") == today:
        return {"status": "already", "state": state}
    symbols = await providers.exchange.perp_universe(
        top=int(merged["universe"]), min_volume_usd=float(merged["min_volume_usd"])
    )
    days = max(30, int(merged["lookback"]) + 10)
    funding_map = await fetch_funding_map(providers, symbols, days=days)
    if not funding_map:
        return {"status": "no_data", "reason": "Fonlama verisi alinamadi"}
    ranking = rank_funding(
        funding_map,
        top_n=int(merged["top_n"]),
        lookback=int(merged["lookback"]),
        min_avg=float(merged.get("min_avg", 0.0)),
        max_avg=merged.get("max_avg"),
        as_of=today,
    )
    new_state = apply_step(
        state, funding_map, merged, today, ranking=ranking, note=f"{len(funding_map)} coin tarandi"
    )
    if new_state is not state:
        db.carry_state_save(new_state)
    return {"status": "ok", "state": new_state}


def status(db) -> dict[str, Any]:
    """Paper durum ozeti: son state, gunluk seri, sonraki rebalance ve edge sagligi."""
    state = db.carry_state_latest()
    series = db.carry_state_series(limit=365)
    edge = None
    net = None
    recent = series[-30:]
    if len(recent) >= 5:
        gross_daily = sum(float(row.get("funding_income") or 0.0) for row in recent) / len(recent)
        net_daily = sum(float(row.get("daily_return") or 0.0) for row in recent) / len(recent)
        edge = round(gross_daily * 365, 4)
        net = round(net_daily * 365, 4)
    snapshot = {
        "state": state,
        "series": series,
        "next_rebalance": next_rebalance_date(state),
        "edge_30d_annual": edge,
        "net_30d_annual": net,
        "defaults": CARRY_DEFAULTS,
    }
    snapshot["alert"] = edge_alert(snapshot)
    return snapshot
