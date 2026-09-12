"""Teknik analiz modulu: indikatörler, formasyonlar, destek/direnç, fibonacci."""

from __future__ import annotations

from crypto_deep_research.analysis.base import AnalysisContext
from crypto_deep_research.analysis.indicators import (
    candle_patterns,
    compute_levels,
    detect_chart_patterns,
    indicator_score,
    indicator_snapshot,
    to_dataframe,
)
from crypto_deep_research.models import AnalysisResult
from crypto_deep_research.providers.base import source


async def analyze_technical(ctx: AnalysisContext) -> AnalysisResult:
    klines = await ctx.klines(500)
    if len(klines) < 30:
        return ctx.result(
            "technical",
            "Teknik Analiz",
            status="no_data",
            summary="Yeterli OHLCV verisi alınamadı.",
            sources=[source("Binance", "https://api.binance.com", note="OHLCV")],
        )
    df = to_dataframe(klines)
    snapshot = indicator_snapshot(df)
    score, confidence, reasons = indicator_score(snapshot)
    candles = candle_patterns(df)
    chart_patterns = detect_chart_patterns(df)
    levels = compute_levels(df, snapshot["price"])

    pattern_score = 0.0
    for pattern in candles + chart_patterns:
        lower = pattern.lower()
        if any(word in lower for word in ("bullish", "dip", "yükseliş", "kırılımı (breakout)", "double bottom")):
            pattern_score += 0.15
        if any(word in lower for word in ("bearish", "tepe", "düşüş", "breakdown", "double top")):
            pattern_score -= 0.15
    score = max(-1.0, min(1.0, score * 0.8 + pattern_score))

    distance_resistance = levels.get("distance_to_resistance_pct")
    distance_support = levels.get("distance_to_support_pct")
    if distance_resistance is not None and distance_resistance < 1.5:
        reasons.append(f"Direnç bölgesine çok yakın (%{distance_resistance:.2f})")
        confidence = min(1.0, confidence + 0.05)
    if distance_support is not None and distance_support < 1.5:
        reasons.append(f"Destek bölgesine çok yakın (%{distance_support:.2f})")

    summary = (
        f"Fiyat {snapshot['price']:.6g}; RSI {snapshot.get('rsi_14', 0):.1f}, "
        f"MACD histogram {snapshot.get('macd_histogram', 0):.4g}. "
        f"En yakın destek {levels.get('nearest_support')}, en yakın direnç {levels.get('nearest_resistance')}."
    )
    if candles:
        summary += " Mum formasyonları: " + ", ".join(candles) + "."
    if chart_patterns:
        summary += " Grafik formasyonları: " + ", ".join(chart_patterns) + "."

    sources = [source("Binance", "https://api.binance.com", note=f"OHLCV {ctx.timeframe}")]
    if not any(True for _ in klines if _.volume) or not klines:
        sources.append(source("CoinGecko", "https://api.coingecko.com", note="OHLC yedek"))

    return ctx.result(
        "technical",
        "Teknik Analiz",
        summary=summary,
        data={
            "indicators": snapshot,
            "levels": levels,
            "candle_patterns": candles,
            "chart_patterns": chart_patterns,
            "reasons": reasons,
            "kline_count": len(klines),
        },
        sources=sources,
        score=round(score, 4),
        confidence=round(confidence, 3),
    )
