"""Likidasyon haritası ve türev piyasa analizi."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from crypto_deep_research.analysis.base import AnalysisContext, clamp
from crypto_deep_research.formatting import price as fmt_price
from crypto_deep_research.models import AnalysisResult
from crypto_deep_research.providers.base import source

logger = logging.getLogger(__name__)

LEVERAGE_TIERS = [(10, 0.40), (25, 0.25), (50, 0.20), (100, 0.15)]


def _liquidation_map(price: float, open_interest_usd: float | None) -> list[dict[str, Any]]:
    """Open interest ve kaldıraç kademelerinden yaklaşık likidasyon seviyeleri."""
    if not price or not open_interest_usd:
        return []
    levels: list[dict[str, Any]] = []
    for leverage, share in LEVERAGE_TIERS:
        notional = open_interest_usd * share
        long_liq = price * (1 - 1 / leverage)
        short_liq = price * (1 + 1 / leverage)
        levels.append(
            {
                "leverage": leverage,
                "side": "long",
                "price": long_liq,
                "distance_pct": round((long_liq / price - 1) * 100, 2),
                "notional_usd": round(notional * 0.5),
                "share_of_oi": round(share * 0.5, 3),
            }
        )
        levels.append(
            {
                "leverage": leverage,
                "side": "short",
                "price": short_liq,
                "distance_pct": round((short_liq / price - 1) * 100, 2),
                "notional_usd": round(notional * 0.5),
                "share_of_oi": round(share * 0.5, 3),
            }
        )
    levels.sort(key=lambda item: item["price"])
    return levels


async def analyze_liquidations(ctx: AnalysisContext) -> AnalysisResult:
    snapshot = await ctx.snapshot()
    price = snapshot.price_usd
    symbol = ctx.coin.symbol
    sources = [
        source("Binance Futures", "https://fapi.binance.com", note="open interest, funding"),
        source("Coinalyze", "https://coinalyze.net", note="likidasyon geçmişi"),
    ]

    perp_symbol = ctx.providers.exchange.perp_symbol(symbol)
    perp_multiplier = ctx.providers.exchange.perp_multiplier(perp_symbol)
    tasks = {
        "funding": ctx.providers.exchange.binance_funding(symbol, perp_symbol=perp_symbol),
        "oi": ctx.providers.exchange.binance_open_interest(symbol, perp_symbol=perp_symbol),
        "ls_ratio": ctx.providers.exchange.binance_long_short_ratio(symbol, perp_symbol=perp_symbol),
    }
    if ctx.providers.coinalyze.enabled:
        tasks["liq_history"] = ctx.providers.coinalyze.liquidation_history(symbol, hours=48)
        tasks["oi_history"] = ctx.providers.coinalyze.open_interest_history(symbol, hours=72)
        tasks["ls_history"] = ctx.providers.coinalyze.long_short_history(symbol, hours=48)
        tasks["funding_history"] = ctx.providers.coinalyze.funding_history(symbol, hours=72)

    results = await asyncio.gather(*tasks.values(), return_exceptions=True)
    data: dict[str, Any] = {"perp_symbol": perp_symbol}
    for key, value in zip(tasks.keys(), results, strict=False):
        if isinstance(value, Exception):
            logger.debug("likidasyon verisi alınamadı (%s): %s", key, value)
            continue
        data[key] = value

    oi_amount = data.get("oi")
    oi_usd = float(oi_amount) * perp_multiplier * price if oi_amount else None
    if oi_usd:
        data["open_interest_usd_estimate"] = oi_usd

    liquidation_levels = _liquidation_map(price, oi_usd)
    data["liquidation_levels"] = liquidation_levels

    score = 0.0
    confidence = 0.0
    reasons: list[str] = []

    funding = data.get("funding")
    if funding is not None:
        confidence += 0.2
        annualized = funding * 3 * 365 * 100
        data["funding_annualized_pct"] = round(annualized, 2)
        if funding > 0.0005:
            score -= 0.4
            reasons.append(f"Funding yüksek pozitif ({annualized:.1f}% yıllık): long'lar kalabalik")
        elif funding < -0.0005:
            score += 0.4
            reasons.append(f"Funding negatif ({annualized:.1f}% yıllık): short'lar kalabalik, short squeeze riski")

    ls_ratio = data.get("ls_ratio")
    if ls_ratio is not None:
        confidence += 0.15
        data["long_short_ratio"] = ls_ratio
        if ls_ratio > 2.0:
            score -= 0.3
            reasons.append(f"Long/short oranı {ls_ratio:.2f}: aşırı long iyimserligi")
        elif ls_ratio < 0.8:
            score += 0.3
            reasons.append(f"Long/short oranı {ls_ratio:.2f}: aşırı short kötümserligi")

    liq_history = data.get("liq_history") or []
    if liq_history:
        confidence += 0.25
        long_total = sum(float(row.get("l") or 0) for row in liq_history)
        short_total = sum(float(row.get("s") or 0) for row in liq_history)
        data["liquidations_long_usd_48h"] = long_total
        data["liquidations_short_usd_48h"] = short_total
        data["liquidations_total_usd_48h"] = long_total + short_total
        if long_total + short_total > 0:
            short_share = short_total / (long_total + short_total)
            data["short_liquidation_share"] = round(short_share, 3)
            if short_share > 0.6:
                score += 0.35
                reasons.append("Son likidasyonların çoğu short: yukari baskı (short squeeze)")
            elif short_share < 0.4:
                score -= 0.35
                reasons.append("Son likidasyonların çoğu long: aşağı baskı (long flush)")
        biggest = max(liq_history, key=lambda row: float(row.get("l") or 0) + float(row.get("s") or 0))
        data["biggest_liquidation_hour"] = {
            "time": datetime.fromtimestamp(int(biggest.get("t", 0)), tz=timezone.utc).isoformat()
            if biggest.get("t")
            else None,
            "long_usd": float(biggest.get("l") or 0),
            "short_usd": float(biggest.get("s") or 0),
        }
    else:
        reasons.append("Gerçek likidasyon geçmişi için Coinalyze anahtari yok; seviyeler OI tahmini")

    oi_history = data.get("oi_history") or []
    if oi_history:
        try:
            first = float(oi_history[0].get("c") or 0)
            last = float(oi_history[-1].get("c") or 0)
            if first:
                change = (last / first - 1) * 100
                data["open_interest_change_72h_pct"] = round(change, 2)
                if change > 10 and price:
                    reasons.append(f"Açık pozisyon (OI) 72 saatte %{change:.1f} arttı: kaldıraç birikimi")
        except (ValueError, TypeError, IndexError):
            pass

    status = "ok" if oi_amount is not None or liq_history else "partial"
    nearest_levels = sorted(
        [lvl for lvl in liquidation_levels],
        key=lambda item: abs(item["distance_pct"]),
    )[:6]
    if nearest_levels:
        summary = (
            f"Fiyat {fmt_price(price)}. En yakın likidasyon seviyeleri: "
            + ", ".join(
                f"{fmt_price(lvl['price'])} ({lvl['side']} {lvl['leverage']}x)"
                for lvl in nearest_levels[:4]
            )
            + "."
        )
    elif oi_amount is not None:
        summary = (
            f"Fiyat {fmt_price(price)}. Açık pozisyon verisi alındı ancak likidasyon "
            "kümeleri hesaplanamadı."
        )
    else:
        summary = (
            f"{symbol.upper()} için Binance vadeli piyasasında veri bulunamadı "
            "(1000x kontrat eşlemesi denendi)."
        )

    return ctx.result(
        "liquidations",
        "Likidasyon Haritası ve Türev Piyasalar",
        status=status,
        summary=summary,
        data={"reasons": reasons, **{k: v for k, v in data.items() if k != "liq_history"}},
        sources=sources,
        score=round(clamp(score), 4),
        confidence=round(min(confidence, 1.0), 3),
        warnings=[] if ctx.providers.coinalyze.enabled else ["Coinalyze anahtari yok: likidasyon geçmişi sınırlı."],
    )
