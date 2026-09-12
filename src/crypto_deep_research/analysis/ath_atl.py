"""ATH/ATL analizi: dolar bazlı tarihsel zirve/dip mesafeleri ve yerel aralık konumu."""

from __future__ import annotations

from crypto_deep_research.analysis.base import AnalysisContext, clamp
from crypto_deep_research.analysis.indicators import to_dataframe
from crypto_deep_research.formatting import pct
from crypto_deep_research.formatting import price as fmt_price
from crypto_deep_research.models import AnalysisResult
from crypto_deep_research.providers.base import source


async def analyze_ath_atl(ctx: AnalysisContext) -> AnalysisResult:
    snapshot = await ctx.snapshot()
    sources = [
        source("CoinGecko", "https://www.coingecko.com", note="ATH/ATL ve tarihleri"),
        source("Binance", "https://api.binance.com", note="yerel aralık"),
    ]
    price = snapshot.price_usd
    data: dict[str, object] = {
        "price_usd": price,
        "ath_usd": snapshot.ath_usd,
        "ath_date": snapshot.ath_date.isoformat() if snapshot.ath_date else None,
        "distance_from_ath_pct": snapshot.distance_from_ath_pct,
        "ath_change_pct": snapshot.ath_change_pct,
        "atl_usd": snapshot.atl_usd,
        "atl_date": snapshot.atl_date.isoformat() if snapshot.atl_date else None,
        "distance_from_atl_pct": snapshot.distance_from_atl_pct,
        "atl_change_pct": snapshot.atl_change_pct,
    }

    klines = await ctx.klines(500)
    local_high = local_low = None
    percentile = None
    if len(klines) >= 30:
        df = to_dataframe(klines)
        local_high = float(df["high"].max())
        local_low = float(df["low"].min())
        percentile = (price - local_low) / (local_high - local_low) if local_high > local_low else None
        data.update(
            {
                "local_high": local_high,
                "local_low": local_low,
                "distance_from_local_high_pct": round((price / local_high - 1) * 100, 2),
                "distance_from_local_low_pct": round((price / local_low - 1) * 100, 2),
                "position_in_local_range": round(percentile, 4) if percentile is not None else None,
                "kline_days": len(df),
            }
        )
    ctx.db.record_metric(ctx.coin.id, "price", float(price))

    score = 0.0
    confidence = 0.4
    reasons: list[str] = []

    distance_ath = snapshot.distance_from_ath_pct
    if distance_ath is not None:
        confidence += 0.2
        if distance_ath < -80:
            score += 0.35
            reasons.append(f"ATH'in %{abs(distance_ath):.0f} altında: derin değer kaybı, toparlanma potansiyeli")
        elif distance_ath < -50:
            score += 0.2
            reasons.append(f"ATH'in %{abs(distance_ath):.0f} altında: uzun vadeli iskonto")
        elif distance_ath > -8:
            score -= 0.2
            reasons.append("ATH'e %8'den yakın: satış baskısı bölgesi")

    distance_atl = snapshot.distance_from_atl_pct
    if distance_atl is not None:
        confidence += 0.1
        if distance_atl < 50:
            score -= 0.3
            reasons.append("ATL'e çok yakın: pazar güveni çok zayıf")

    if percentile is not None:
        confidence += 0.2
        if percentile < 0.15:
            score += 0.3
            reasons.append(f"Yerel aralığın alt %{percentile * 100:.0f}'inde (destek bölgesi)")
        elif percentile > 0.9:
            score -= 0.1
            reasons.append(f"Yerel aralığın üst %{(1 - percentile) * 100:.0f}'inde (direnç bölgesi)")

    if distance_ath is not None and percentile is not None:
        momentum = snapshot.change_30d_pct
        if momentum is not None and momentum > 10 and percentile > 0.6:
            score += 0.15
            reasons.append("Yüksek konum + pozitif 30g momentum: trend devam edebilir")

    summary = (
        f"Fiyat {fmt_price(price)}. ATH'e uzaklık {pct(distance_ath)}, "
        f"ATL'e uzaklık {pct(distance_atl)}."
        if distance_ath is not None and distance_atl is not None
        else f"Fiyat {fmt_price(price)}; ATH/ATL verisi kısmi."
    )
    if percentile is not None:
        summary += f" Yerel 500 mum aralık konumu: %{percentile * 100:.0f}."

    return ctx.result(
        "ath_atl",
        "USD Bazlı ATH ve ATL Mesafesi",
        summary=summary,
        data={"reasons": reasons, **data},
        sources=sources,
        score=round(clamp(score), 4),
        confidence=round(min(confidence, 1.0), 3),
    )
