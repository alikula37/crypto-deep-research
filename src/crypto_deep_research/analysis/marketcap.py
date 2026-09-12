"""Piyasa değeri analizi: geçmiş mcap ile oran, kendi tarihine göre konum."""

from __future__ import annotations

from statistics import mean

from crypto_deep_research.analysis.base import AnalysisContext, clamp, trend_score
from crypto_deep_research.models import AnalysisResult
from crypto_deep_research.providers.base import ProviderError, source


async def analyze_marketcap(ctx: AnalysisContext) -> AnalysisResult:
    snapshot = await ctx.snapshot()
    sources = [source("CoinGecko", "https://www.coingecko.com", note="geçmiş piyasa değeri serisi")]
    try:
        chart = await ctx.providers.coingecko.market_chart(ctx.coin.id, days=365)
    except ProviderError:
        chart = {}

    market_caps = [float(pair[1]) for pair in chart.get("market_caps") or [] if pair and pair[1]]
    current_mcap = snapshot.market_cap_usd
    if not market_caps or not current_mcap:
        return ctx.result(
            "marketcap",
            "Geçmiş Mcap / Güncel Mcap Oranı",
            status="no_data",
            summary="Geçmiş piyasa değeri serisi alınamadı.",
            sources=sources,
        )

    ctx.db.record_metric(ctx.coin.id, "market_cap", float(current_mcap))

    def _ago(days: int) -> float | None:
        idx = len(market_caps) - days - 1
        if 0 <= idx < len(market_caps):
            return market_caps[idx]
        return None

    ratio_7d = current_mcap / _ago(7) if _ago(7) else None
    ratio_30d = current_mcap / _ago(30) if _ago(30) else None
    ratio_90d = current_mcap / _ago(90) if _ago(90) else None
    ratio_365d = current_mcap / _ago(365) if _ago(365) else None
    avg_mcap = mean(market_caps)
    max_mcap = max(market_caps)
    min_mcap = min(market_caps)
    percentile = sum(1 for value in market_caps if value <= current_mcap) / len(market_caps)
    drawdown_from_max = (current_mcap / max_mcap - 1) * 100 if max_mcap else None
    ratio_vs_avg = current_mcap / avg_mcap if avg_mcap else None

    history = ctx.db.metric_history(ctx.coin.id, "market_cap", limit=180)
    recorded_values = [row["value"] for row in history[1:]] if len(history) > 1 else []
    history_percentile = None
    if len(recorded_values) >= 3:
        history_percentile = sum(1 for v in recorded_values if v <= current_mcap) / len(recorded_values)

    score = 0.0
    confidence = 0.35
    reasons: list[str] = []

    if percentile < 0.2:
        score += 0.4
        reasons.append(
            f"Güncel mcap 365 günlük aralığın alt %{percentile * 100:.0f}'inde: kendi tarihine göre düşük"
        )
    elif percentile > 0.85:
        score -= 0.1
        reasons.append(
            f"Güncel mcap 365 günlük aralığın üst %{(1 - percentile) * 100:.0f}'inde: tarihsel zirveye yakın"
        )
    else:
        reasons.append(f"Mcap 365 günlük aralıkta %{percentile * 100:.0f}. yüzdelikte")

    if ratio_30d is not None:
        confidence += 0.2
        trend_component = trend_score(snapshot.change_30d_pct, 30.0) * 0.3
        score += trend_component
        direction = "üzerinde" if ratio_30d > 1 else "altında"
        reasons.append(f"Güncel mcap 30 gün önceki mcap'in %{abs(ratio_30d - 1) * 100:.1f} {direction}")

    if drawdown_from_max is not None:
        confidence += 0.15
        if drawdown_from_max < -70:
            score += 0.2
            reasons.append(f"Mcap zirvesinden %{abs(drawdown_from_max):.0f} aşağıda: uzun vadeli toparlanma potansiyeli")
        elif drawdown_from_max > -5:
            score -= 0.15
            reasons.append("Mcap neredeyse tarihsel zirvede: sınırlı yukari alan")

    if ratio_vs_avg is not None:
        confidence += 0.1
        if ratio_vs_avg < 0.6:
            score += 0.15
            reasons.append(f"Mcap 365 gün ortalamasının %{(ratio_vs_avg - 1) * 100:.0f} altında")
        elif ratio_vs_avg > 1.5:
            score -= 0.1
            reasons.append(f"Mcap 365 gün ortalamasının %{(ratio_vs_avg - 1) * 100:.0f} üzerinde")

    summary = (
        f"Güncel mcap ${current_mcap:,.0f}; 30 gün oranı {ratio_30d and f'{ratio_30d:.3f}' or 'n/a'}, "
        f"365 günlük yüzdelik {percentile * 100:.0f}, zirveden uzaklık %{drawdown_from_max:.1f}."
    )

    return ctx.result(
        "marketcap",
        "Geçmiş Mcap / Güncel Mcap Oranı",
        summary=summary,
        data={
            "current_market_cap_usd": current_mcap,
            "avg_market_cap_365d_usd": avg_mcap,
            "max_market_cap_365d_usd": max_mcap,
            "min_market_cap_365d_usd": min_mcap,
            "ratio_vs_7d": ratio_7d,
            "ratio_vs_30d": ratio_30d,
            "ratio_vs_90d": ratio_90d,
            "ratio_vs_365d": ratio_365d,
            "ratio_vs_365d_avg": ratio_vs_avg,
            "percentile_365d": round(percentile, 4),
            "drawdown_from_max_pct": round(drawdown_from_max, 2) if drawdown_from_max is not None else None,
            "stored_history_percentile": history_percentile,
            "reasons": reasons,
        },
        sources=sources,
        score=round(clamp(score), 4),
        confidence=round(min(confidence, 1.0), 3),
    )
