"""Ileri getiri etiketleyici: bekleyen outcome satirlarini doldurur."""

from __future__ import annotations

import logging
import time
from datetime import date
from typing import Any

from crypto_deep_research.deep_research.accuracy import close_for_date, fetch_closes

logger = logging.getLogger(__name__)

MISSING_GRACE_SECONDS = 3 * 86_400


async def fill_due_outcomes(
    providers: Any,
    db: Any,
    *,
    limit: int = 50,
    max_attempts: int = 14,
) -> dict[str, int]:
    """Vadesi gelen outcome satirlarini Binance (yedek: CoinGecko) kapanislariyla doldurur."""
    due = db.outcomes_due(limit=limit)
    if not due:
        return {"due": 0, "filled": 0, "missing": 0, "pending": 0}

    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in due:
        symbol = (row.get("symbol") or row["coin"]).upper()
        groups.setdefault((symbol, row["coin"]), []).append(row)

    filled = missing = pending = 0
    for (symbol, _coin), rows in groups.items():
        start = min(row["entry_at"] for row in rows) - 2 * 86_400
        end = max(row["due_at"] for row in rows) + 6 * 86_400
        closes: dict[date, float] = {}
        try:
            closes = await fetch_closes(providers, symbol, int(start * 1000), int(end * 1000))
        except Exception:
            logger.warning("Outcome kapanislari alinamadi: %s", symbol)
        for row in rows:
            target = date.fromisoformat(row["target_date"])
            exit_price = close_for_date(closes, target)
            entry_price = row.get("entry_price")
            if exit_price and entry_price:
                return_pct = round((exit_price / entry_price - 1) * 100, 4)
                direction = row.get("direction_at_run") or "neutral"
                hit = None
                if direction == "up":
                    hit = 1 if return_pct > 0 else 0
                elif direction == "down":
                    hit = 1 if return_pct < 0 else 0
                db.outcome_mark_filled(
                    row["run_id"],
                    row["horizon_days"],
                    exit_price=exit_price,
                    return_pct=return_pct,
                    hit=hit,
                    price_source="binance",
                )
                filled += 1
                continue
            attempts = int(row.get("attempts") or 0) + 1
            if attempts >= max_attempts and time.time() > row["due_at"] + MISSING_GRACE_SECONDS:
                db.outcome_mark_failure(
                    row["run_id"], row["horizon_days"], "missing", "Kapanis verisi bulunamadi."
                )
                missing += 1
            else:
                db.outcome_mark_failure(
                    row["run_id"], row["horizon_days"], "pending", "Kapanis henuz yok."
                )
                pending += 1

    return {"due": len(due), "filled": filled, "missing": missing, "pending": pending}
