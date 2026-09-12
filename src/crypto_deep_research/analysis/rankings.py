"""Piyasa değeri sıralaması: güncel rank, geçmiş max/min rank mesafesi."""

from __future__ import annotations

from typing import Any

from crypto_deep_research.analysis.base import AnalysisContext, clamp
from crypto_deep_research.models import AnalysisResult
from crypto_deep_research.providers.base import ProviderError, source


async def analyze_rankings(ctx: AnalysisContext) -> AnalysisResult:
    snapshot = await ctx.snapshot()
    sources = [source("CoinGecko", "https://www.coingecko.com", note="mcap sıralaması (top 300)")]
    current_rank = snapshot.rank
    current_mcap = snapshot.market_cap_usd
    if current_rank is None or not current_mcap:
        return ctx.result(
            "rankings",
            "Mcap Sıralaması ve Geçmiş Uzaklık",
            status="no_data",
            summary="Sıralama verisi alınamadı.",
            sources=sources,
        )

    try:
        pages = await ctx.providers.coingecko.markets(per_page=100, page=1)
        markets = list(pages)
        if current_rank > 100:
            for page in (2, 3):
                extra = await ctx.providers.coingecko.markets(per_page=100, page=page)
                markets.extend(extra)
    except ProviderError:
        markets = []

    top_mcaps = [float(m.get("market_cap") or 0) for m in markets if m.get("market_cap")]
    universe = len(top_mcaps) or 300
    mcap_percentile = (
        sum(1 for value in top_mcaps if value <= current_mcap) / len(top_mcaps)
        if top_mcaps
        else None
    )

    ctx.db.record_metric(ctx.coin.id, "rank", float(current_rank))
    history = ctx.db.metric_history(ctx.coin.id, "rank", limit=365)
    ranks = [row["value"] for row in history]
    best_rank = min(ranks) if ranks else None
    worst_rank = max(ranks) if ranks else None
    rank_change = (ranks[0] - ranks[-1]) if len(ranks) > 1 else None
    distance_from_best = (current_rank - best_rank) if best_rank else None
    distance_from_worst = (worst_rank - current_rank) if worst_rank else None

    score = 0.0
    confidence = 0.35
    reasons: list[str] = []

    if current_rank <= 10:
        score += 0.3
        reasons.append(f"#{current_rank}: en büyük 10 varlık arasında")
    elif current_rank <= 50:
        score += 0.15
        reasons.append(f"#{current_rank}: ilk 50 içinde")
    elif current_rank > 200:
        score -= 0.2
        reasons.append(f"#{current_rank}: 200+. sirada, likidite riski")

    if rank_change is not None:
        confidence += 0.25
        if rank_change > 0:
            score += 0.35
            reasons.append(f"Rank geçmişe göre {rank_change:.0f} sira iyilesti")
        elif rank_change < 0:
            score -= 0.35
            reasons.append(f"Rank geçmişe göre {abs(rank_change):.0f} sira kötülesti")
    else:
        reasons.append("Geçmiş rank verisi birikiyor; sonraki kosularda karşılaştırma yapılacak")

    if distance_from_best is not None:
        data_best = {
            "best_rank_seen": int(best_rank),
            "worst_rank_seen": int(worst_rank),
            "distance_from_best_rank": int(distance_from_best),
            "distance_from_worst_rank": int(distance_from_worst) if distance_from_worst is not None else None,
            "observation_count": len(ranks),
        }
    else:
        data_best = {"observation_count": len(ranks)}

    if mcap_percentile is not None:
        confidence += 0.2
        reasons.append(f"Top {universe} içinde mcap yüzdeliği %{mcap_percentile * 100:.0f}")

    summary = f"Güncel sıralama #{current_rank}."
    if best_rank and worst_rank and len(set(ranks)) > 1:
        summary += f" Gözlenen en iyi #{int(best_rank)}, en kötü #{int(worst_rank)}."
    elif len(ranks) <= 1:
        summary += " Geçmiş sıralama verisi henüz birikmedi."
    if mcap_percentile is not None:
        summary += f" Top {universe} mcap yüzdeliği %{mcap_percentile * 100:.0f}."

    data: dict[str, Any] = {
        "rank": current_rank,
        "market_cap_usd": current_mcap,
        "universe_size": universe,
        "mcap_percentile_in_top300": round(mcap_percentile, 4) if mcap_percentile is not None else None,
        "rank_change_first_to_last": rank_change,
        "reasons": reasons,
        **data_best,
    }

    return ctx.result(
        "rankings",
        "Coinler Arasi Mcap Sıralaması",
        summary=summary,
        data=data,
        sources=sources,
        score=round(clamp(score), 4),
        confidence=round(min(confidence, 1.0), 3),
    )
