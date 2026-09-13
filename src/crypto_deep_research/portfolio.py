"""Portfoy degerleme: manuel pozisyonlari guncel fiyatlarla birlestirir."""

from __future__ import annotations

from typing import Any


def compute_portfolio(
    entries: list[dict[str, Any]], prices: dict[str, float | None]
) -> dict[str, Any]:
    """Pozisyonlari degerler; fiyati olmayanlar 'deger yok' olarak isaretlenir."""
    positions: list[dict[str, Any]] = []
    total_value = 0.0
    total_cost = 0.0
    for entry in entries:
        amount = float(entry.get("amount") or 0)
        entry_price = float(entry.get("entry_price") or 0)
        cost = amount * entry_price
        current_price = prices.get(entry["coin"])
        value = amount * current_price if current_price is not None else None
        pnl = value - cost if value is not None else None
        pnl_pct = (pnl / cost * 100) if (pnl is not None and cost) else None
        if value is not None:
            total_value += value
        total_cost += cost
        positions.append(
            {
                **entry,
                "cost_usd": round(cost, 2),
                "current_price": current_price,
                "value_usd": round(value, 2) if value is not None else None,
                "pnl_usd": round(pnl, 2) if pnl is not None else None,
                "pnl_pct": round(pnl_pct, 2) if pnl_pct is not None else None,
            }
        )
    for position in positions:
        position["allocation_pct"] = (
            round(position["value_usd"] / total_value * 100, 2)
            if position["value_usd"] is not None and total_value
            else None
        )
    total_pnl = total_value - total_cost if positions else 0.0
    return {
        "positions": positions,
        "totals": {
            "value_usd": round(total_value, 2),
            "cost_usd": round(total_cost, 2),
            "pnl_usd": round(total_pnl, 2),
            "pnl_pct": round(total_pnl / total_cost * 100, 2) if total_cost else None,
            "positions": len(positions),
        },
    }


async def value_portfolio(providers: Any, db: Any) -> dict[str, Any]:
    """DB'deki pozisyonlari guncel fiyatlarla degerler."""
    entries = db.portfolio_list()
    prices: dict[str, float | None] = {}
    for coin in {entry["coin"] for entry in entries}:
        try:
            ref = await providers.coingecko.resolve(coin)
            snapshot = await providers.coingecko.snapshot(ref)
            prices[coin] = snapshot.price_usd
        except Exception:
            prices[coin] = None
    return compute_portfolio(entries, prices)
