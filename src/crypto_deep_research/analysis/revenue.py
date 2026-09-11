"""Gelir/fee analizi: DefiLlama ucret ve protokol gelirleri, fee/mcap orani."""

from __future__ import annotations

import asyncio
from typing import Any

from crypto_deep_research.analysis.base import AnalysisContext, clamp
from crypto_deep_research.models import AnalysisResult
from crypto_deep_research.providers.base import source


async def analyze_revenue(ctx: AnalysisContext) -> AnalysisResult:
    snapshot = await ctx.snapshot()
    sources = [
        source("DefiLlama", "https://defillama.com/fees", note="protokol/zincir ucret ve gelirleri")
    ]
    fees_task = ctx.providers.defillama.fees_summary(ctx.coin.id, "dailyFees")
    revenue_task = ctx.providers.defillama.fees_summary(ctx.coin.id, "dailyRevenue")
    fees, revenue = await asyncio.gather(fees_task, revenue_task, return_exceptions=True)

    def _normalize(value: Any) -> dict[str, Any]:
        if isinstance(value, Exception) or not value:
            return {}
        if isinstance(value, list):
            for entry in value:
                if isinstance(entry, dict) and str(entry.get("name", "")).lower() == ctx.coin.name.lower():
                    return entry
            return value[0] if value and isinstance(value[0], dict) else {}
        if isinstance(value, dict):
            return value
        return {}

    fee_data = _normalize(fees)
    revenue_data = _normalize(revenue)
    summary_data = ctx.providers.defillama.summarize_fees(fee_data)
    revenue_summary = ctx.providers.defillama.summarize_fees(revenue_data)

    if not summary_data and not revenue_summary:
        return ctx.result(
            "revenue",
            "Gelirler, Fee'ler ve Mcap Orani",
            status="no_data",
            summary=f"{ctx.coin.name} icin DefiLlama ucret/gelir verisi bulunamadi.",
            sources=sources,
        )

    mcap = snapshot.market_cap_usd or 0
    daily_fees = summary_data.get("total_24h_usd") or summary_data.get("average_24h_usd")
    annualized_fees = daily_fees * 365 if daily_fees else None
    fee_yield = (annualized_fees / mcap * 100) if (annualized_fees and mcap) else None
    revenue_daily = revenue_summary.get("revenue_24h_usd") or revenue_summary.get("total_24h_usd")
    annualized_revenue = revenue_daily * 365 if revenue_daily else None
    revenue_yield = (annualized_revenue / mcap * 100) if (annualized_revenue and mcap) else None

    score = 0.0
    confidence = 0.0
    reasons: list[str] = []

    if fee_yield is not None:
        confidence += 0.4
        if fee_yield >= 5:
            score += 0.5
            reasons.append(f"Yillik fee getirisi %{fee_yield:.2f}: guclu nakit uretimi")
        elif fee_yield >= 1:
            score += 0.2
            reasons.append(f"Yillik fee getirisi %{fee_yield:.2f}: makul")
        elif fee_yield < 0.2:
            score -= 0.3
            reasons.append(f"Yillik fee getirisi %{fee_yield:.3f}: zayif")

    change_7d = summary_data.get("change_7d_pct")
    if change_7d is not None:
        confidence += 0.25
        if change_7d > 10:
            score += 0.25
            reasons.append(f"Fee'ler 7 gunde %{change_7d:.1f} artti: kullanim artisi")
        elif change_7d < -10:
            score -= 0.25
            reasons.append(f"Fee'ler 7 gunde %{change_7d:.1f} azaldi: kullanim dususu")

    if revenue_yield is not None:
        confidence += 0.15
        data_note = f"Yillik gelir getirisi %{revenue_yield:.2f}"
        reasons.append(data_note)

    summary = (
        f"Gunluk fee ${daily_fees:,.0f}" if daily_fees else "Gunluk fee verisi yok"
    )
    if annualized_fees:
        summary += f" (yillik ~${annualized_fees:,.0f})"
    if fee_yield is not None:
        summary += f"; fee/mcap getirisi %{fee_yield:.2f}"
    if revenue_daily:
        summary += f"; gunluk gelir ${revenue_daily:,.0f}"

    return ctx.result(
        "revenue",
        "Gelirler, Fee'ler ve Mcap Orani",
        summary=summary,
        data={
            "fees": summary_data,
            "revenue": revenue_summary,
            "daily_fees_usd": daily_fees,
            "annualized_fees_usd": annualized_fees,
            "fee_yield_pct": round(fee_yield, 4) if fee_yield is not None else None,
            "revenue_yield_pct": round(revenue_yield, 4) if revenue_yield is not None else None,
            "market_cap_usd": mcap or None,
            "reasons": reasons,
        },
        sources=sources,
        score=round(clamp(score), 4),
        confidence=round(min(confidence, 1.0), 3),
    )
