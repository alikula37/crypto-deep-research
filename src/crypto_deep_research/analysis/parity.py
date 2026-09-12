"""BTC/ETH parite analizi: oran trendi, tarihsel zirve ve direnç mesafesi.

Binance'te doğrudan BTC paritesi yoksa (ör. PEPE/BTC listelenmiyor) CoinGecko'nun
`vs_currency=btc` / `vs_currency=eth` fiyat serileri kullanılır.
"""

from __future__ import annotations

from typing import Any

from crypto_deep_research.analysis.base import AnalysisContext, clamp, trend_score
from crypto_deep_research.analysis.indicators import compute_levels, ema, to_dataframe
from crypto_deep_research.formatting import num, pct
from crypto_deep_research.models import AnalysisResult
from crypto_deep_research.providers.base import ProviderError, source


async def _pair_klines(ctx: AnalysisContext, pair_symbol: str):
    try:
        return await ctx.providers.exchange.klines(pair_symbol, "1d", 1000, quote=None)
    except ProviderError:
        return []


async def _coingecko_ratio(ctx: AnalysisContext, vs_currency: str, days: int = 90) -> dict[str, Any]:
    """CoinGecko fiyat serisinden parite oranı ve trend bilgisi üretir."""
    try:
        chart = await ctx.providers.coingecko.market_chart(
            ctx.coin.id, days=days, vs_currency=vs_currency
        )
    except ProviderError:
        return {}
    prices = [float(pair[1]) for pair in chart.get("prices") or [] if pair and pair[1]]
    if len(prices) < 10:
        return {}
    current = prices[-1]
    ago_30 = prices[-(min(30, len(prices)) + 1)] if len(prices) > 30 else None
    change_30d = (current / ago_30 - 1) * 100 if ago_30 else None
    window_high = max(prices)
    window_low = min(prices)
    return {
        f"ratio_now_{vs_currency}": current,
        f"ratio_change_30d_pct_{vs_currency}": round(change_30d, 2) if change_30d is not None else None,
        f"ratio_distance_from_high_pct_{vs_currency}": round((current / window_high - 1) * 100, 2),
        f"ratio_distance_from_low_pct_{vs_currency}": round((current / window_low - 1) * 100, 2),
        f"ratio_high_{vs_currency}": window_high,
        f"ratio_low_{vs_currency}": window_low,
    }


async def analyze_parity(ctx: AnalysisContext) -> AnalysisResult:
    symbol = ctx.coin.symbol.upper()
    sources = [
        source("Binance", "https://api.binance.com", note="parite serileri"),
        source("CoinGecko", "https://www.coingecko.com", note="parite ve dominance"),
    ]
    pair = "ETHBTC" if symbol in ("BTC", "ETH") else f"{symbol}BTC"
    pair_label = "ETH/BTC" if symbol in ("BTC", "ETH") else f"{symbol}/BTC"

    klines = await _pair_klines(ctx, pair)
    dominance = None
    try:
        global_market = await ctx.global_market()
        dominance = global_market.btc_dominance
    except Exception:
        pass

    data: dict[str, Any] = {"pair": pair_label, "btc_dominance": dominance}
    score = 0.0
    confidence = 0.15 if dominance is not None else 0.0
    reasons: list[str] = []
    used_fallback = False

    if klines:
        df = to_dataframe(klines)
        closes = df["close"]
        ratio_now = float(closes.iloc[-1])
        ratio_30d = float(closes.iloc[-31]) if len(closes) > 31 else None
        ratio_90d = float(closes.iloc[-91]) if len(closes) > 91 else None
        ratio_ath = float(df["high"].max())
        ratio_atl = float(df["low"].min())
        ema200 = float(ema(closes, 200).iloc[-1]) if len(closes) >= 150 else None
        levels = compute_levels(df, ratio_now)
        change_30d = (ratio_now / ratio_30d - 1) * 100 if ratio_30d else None
        change_90d = (ratio_now / ratio_90d - 1) * 100 if ratio_90d else None
        distance_ath = (ratio_now / ratio_ath - 1) * 100 if ratio_ath else None
        distance_atl = (ratio_now / ratio_atl - 1) * 100 if ratio_atl else None
        above_ema200 = ratio_now > ema200 if ema200 else None

        data.update(
            {
                "ratio_now": ratio_now,
                "ratio_change_30d_pct": round(change_30d, 2) if change_30d is not None else None,
                "ratio_change_90d_pct": round(change_90d, 2) if change_90d is not None else None,
                "ratio_ath": ratio_ath,
                "ratio_atl": ratio_atl,
                "ratio_distance_from_ath_pct": round(distance_ath, 2) if distance_ath is not None else None,
                "ratio_distance_from_atl_pct": round(distance_atl, 2) if distance_atl is not None else None,
                "ratio_above_ema200": above_ema200,
                "ratio_nearest_resistance": levels.get("nearest_resistance"),
                "ratio_distance_to_resistance_pct": levels.get("distance_to_resistance_pct"),
                "ratio_nearest_support": levels.get("nearest_support"),
            }
        )
        confidence += 0.4

        if symbol == "ETH":
            if change_30d is not None and change_30d > 3:
                score += 0.5
                reasons.append(f"ETH/BTC 30 günde %{change_30d:.1f} yukarıda: ETH göreli güçlü")
            elif change_30d is not None and change_30d < -3:
                score -= 0.5
                reasons.append(f"ETH/BTC 30 günde %{change_30d:.1f} aşağıda: BTC göreli güçlü")
        elif symbol == "BTC":
            if change_30d is not None and change_30d < -3:
                score += 0.4
                reasons.append(f"ETH/BTC düşüyor (%{change_30d:.1f}): sermaye BTC'ye kayıyor")
            elif change_30d is not None and change_30d > 3:
                score -= 0.4
                reasons.append(f"ETH/BTC yükseliyor (%{change_30d:.1f}): BTC'den ETH'e rotasyon")
        else:
            score += trend_score(change_30d, 20.0) * 0.6
            direction = "güçleniyor" if (change_30d or 0) > 0 else "zayıflıyor"
            reasons.append(f"{pair_label} paritesinde coin {direction} (30g %{change_30d or 0:.1f})")

        if above_ema200 is not None:
            if above_ema200:
                score += 0.15
                reasons.append(f"{pair_label} 200 EMA üzerinde")
            else:
                score -= 0.15
                reasons.append(f"{pair_label} 200 EMA altında")
        if distance_ath is not None and distance_ath > -3:
            score -= 0.2
            reasons.append(f"{pair_label} tarihsel zirvesine çok yakın: direnç riski")
    else:
        # Binance paritesi yok: CoinGecko vs_currency fallback
        btc_ratio = await _coingecko_ratio(ctx, "btc", days=90)
        eth_ratio = await _coingecko_ratio(ctx, "eth", days=90)
        if btc_ratio:
            used_fallback = True
            confidence += 0.35
            change_30d = btc_ratio.get("ratio_change_30d_pct_btc")
            data.update(btc_ratio)
            data["ratio_source"] = "coingecko_vs_btc"
            if change_30d is not None:
                score += trend_score(change_30d, 20.0) * 0.5
                direction = "güçleniyor" if change_30d > 0 else "zayıflıyor"
                reasons.append(
                    f"Coin/BTC paritesi {direction} (30g {pct(change_30d, signed=True)}, CoinGecko)"
                )
            distance_high = btc_ratio.get("ratio_distance_from_high_pct_btc")
            if distance_high is not None and distance_high > -3:
                score -= 0.15
                reasons.append("Coin/BTC oranı 90 günlük zirvesine çok yakın: direnç riski")
        if eth_ratio:
            data.update(eth_ratio)
            data["ratio_source_eth"] = "coingecko_vs_eth"

    if dominance is not None:
        confidence += 0.15
        data["btc_dominance"] = dominance
        if symbol == "BTC":
            if dominance > 55:
                score += 0.2
                reasons.append(f"BTC dominance %{dominance:.1f}: yüksek, BTC güçlü")
            elif dominance < 45:
                score -= 0.2
                reasons.append(f"BTC dominance %{dominance:.1f}: düşük, altcoin sezonu eğilimi")
        else:
            if dominance > 58:
                score -= 0.2
                reasons.append(f"BTC dominance %{dominance:.1f}: altcoinler için baskı")
            elif dominance < 45:
                score += 0.2
                reasons.append(f"BTC dominance %{dominance:.1f}: altcoinlere sermaye akışı")

    if not klines and not used_fallback:
        return ctx.result(
            "parity",
            "BTC/ETH Paritesi ve Direnç Mesafesi",
            status="no_data",
            summary=(
                f"{symbol} için BTC/ETH parite serisi bulunamadı "
                "(Binance paritesi ve CoinGecko fallback denendi)."
            ),
            data={"btc_dominance": dominance},
            sources=sources,
            score=None,
            confidence=0.05,
        )

    summary_parts: list[str] = []
    if data.get("ratio_now") is not None:
        summary_parts.append(f"Coin/BTC oranı {num(data['ratio_now'], 5)}")
        if data.get("ratio_change_30d_pct") is not None:
            summary_parts.append(f"30g {pct(data['ratio_change_30d_pct'], signed=True)}")
    elif data.get("ratio_now_btc") is not None:
        summary_parts.append(f"Coin/BTC oranı {num(data['ratio_now_btc'], 5)} (CoinGecko)")
        if data.get("ratio_change_30d_pct_btc") is not None:
            summary_parts.append(f"30g {pct(data['ratio_change_30d_pct_btc'], signed=True)}")
    if data.get("ratio_now_eth") is not None:
        summary_parts.append(f"Coin/ETH oranı {num(data['ratio_now_eth'], 5)}")
    if dominance is not None:
        summary_parts.append(f"BTC dominance %{dominance:.1f}")
    if not summary_parts:
        summary_parts.append("Parite verisi kısmi")
    summary = "; ".join(summary_parts) + "."
    if used_fallback:
        summary += " (Binance paritesi yok; CoinGecko kullanıldı.)"

    return ctx.result(
        "parity",
        "BTC/ETH Paritesi ve Direnç Mesafesi",
        summary=summary,
        data={"reasons": reasons, **data},
        sources=sources,
        score=round(clamp(score), 4),
        confidence=round(min(confidence, 1.0), 3),
    )
