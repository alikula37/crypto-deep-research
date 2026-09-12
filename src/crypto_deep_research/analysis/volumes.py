"""Borsa hacim analizi: tüm borsalar, hacim trendi ve fiyat tutarliligi."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any

from crypto_deep_research.analysis.base import AnalysisContext, clamp
from crypto_deep_research.analysis.indicators import to_dataframe
from crypto_deep_research.models import AnalysisResult
from crypto_deep_research.providers.base import source


async def analyze_volumes(ctx: AnalysisContext) -> AnalysisResult:
    snapshot = await ctx.snapshot()
    sources = [
        source("CoinGecko", "https://www.coingecko.com", note="borsa bazlı hacim dagilimi"),
        source("Binance", "https://www.binance.com", note="hacim/fiyat doğrulama"),
        source("OKX", "https://www.okx.com", note="hacim/fiyat doğrulama"),
        source("Bybit", "https://www.bybit.com", note="hacim/fiyat doğrulama"),
    ]

    tickers_task = ctx.providers.coingecko.tickers(ctx.coin.id)
    exchanges_task = ctx.providers.exchange.multi_exchange_tickers(ctx.coin.symbol)
    tickers, exchange_tickers = await asyncio.gather(
        tickers_task, exchanges_task, return_exceptions=True
    )
    if isinstance(tickers, Exception):
        tickers = []
    if isinstance(exchange_tickers, Exception):
        exchange_tickers = {}

    by_exchange: dict[str, float] = defaultdict(float)
    trust_scores: list[float] = []
    for ticker in tickers:
        market = ticker.get("market") or {}
        exchange_name = market.get("name") or ticker.get("market", {}).get("identifier", "?")
        volume_usd = ticker.get("converted_volume", {}).get("usd") or 0.0
        by_exchange[str(exchange_name)] += float(volume_usd)
        trust = ticker.get("trust_score")
        if trust is not None:
            trust_scores.append(float(trust))

    top_exchanges = sorted(by_exchange.items(), key=lambda item: item[1], reverse=True)[:12]
    total_volume = sum(by_exchange.values())
    data: dict[str, Any] = {
        "total_volume_24h_usd": total_volume or snapshot.volume_24h_usd,
        "top_exchanges": [
            {"exchange": name, "volume_usd": round(volume, 2), "share_pct": round(volume / total_volume * 100, 2) if total_volume else None}
            for name, volume in top_exchanges
        ],
        "verified_exchanges": exchange_tickers,
        "avg_trust_score": round(sum(trust_scores) / len(trust_scores), 2) if trust_scores else None,
    }

    price_deviation = None
    if isinstance(exchange_tickers, dict) and len(exchange_tickers) >= 2:
        prices = [v.get("price_usd") for v in exchange_tickers.values() if v.get("price_usd")]
        if len(prices) >= 2:
            mean = sum(prices) / len(prices)
            price_deviation = max(abs(p - mean) / mean for p in prices) * 100
            data["max_price_deviation_pct"] = round(price_deviation, 3)

    score = 0.0
    confidence = 0.0
    reasons: list[str] = []

    mcap = snapshot.market_cap_usd or 0
    volume_24h = total_volume or snapshot.volume_24h_usd or 0
    if mcap and volume_24h:
        turnover = volume_24h / mcap
        data["turnover_ratio"] = round(turnover, 4)
        confidence += 0.2
        if turnover > 0.3:
            score += 0.2
            reasons.append(f"Hacim/mcap oranı {turnover:.2f}: yüksek likidite")
        elif turnover < 0.02:
            score -= 0.2
            reasons.append(f"Hacim/mcap oranı {turnover:.3f}: düşük likidite")

    if price_deviation is not None:
        confidence += 0.15
        if price_deviation > 0.5:
            score -= 0.25
            reasons.append(f"Borsalar arasi fiyat sapması %{price_deviation:.2f}: dikkat")
        else:
            reasons.append(f"Borsalar arasi fiyat tutarli (sapma %{price_deviation:.3f})")

    if isinstance(exchange_tickers, dict) and len(exchange_tickers) >= 2:
        confidence += 0.1
        reasons.append("Binance/OKX/Bybit hacimleri doğrulandi")

    klines = await ctx.klines(300)
    if len(klines) >= 25:
        df = to_dataframe(klines)
        recent_volume = float(df["volume"].tail(5).mean())
        baseline_volume = float(df["volume"].tail(30).mean())
        if baseline_volume:
            volume_change = (recent_volume / baseline_volume - 1) * 100
            data["volume_change_5v30_pct"] = round(volume_change, 2)
            price_change = float(df["close"].iloc[-1] / df["close"].iloc[-6] - 1) * 100 if len(df) > 6 else 0
            confidence += 0.15
            if volume_change > 25 and price_change > 0:
                score += 0.35
                reasons.append("Hacim artışı fiyat yükselişiyle destekleniyor (sağlıklı trend)")
            elif volume_change > 25 and price_change < 0:
                score -= 0.35
                reasons.append("Hacim artışı fiyat düşüşüyle: satış baskısı")
            elif volume_change < -25 and price_change > 0:
                score -= 0.2
                reasons.append("Fiyat artıyor ama hacim düşüyor (zayıf yükseliş)")
            data["price_change_5_candle_pct"] = round(price_change, 2)

    if not by_exchange and not exchange_tickers:
        return ctx.result(
            "volumes",
            "Borsa Hacimleri",
            status="no_data",
            summary="Hacim verisi alınamadı.",
            sources=sources,
        )

    summary = (
        f"24s toplam hacim ~${volume_24h:,.0f}. En büyük borsalar: "
        + ", ".join(f"{name} (${vol:,.0f})" for name, vol in top_exchanges[:4])
    )

    return ctx.result(
        "volumes",
        "Tüm Borsalardaki Hacimler",
        summary=summary,
        data={"reasons": reasons, **data},
        sources=sources,
        score=round(clamp(score), 4),
        confidence=round(min(confidence, 1.0), 3),
    )
