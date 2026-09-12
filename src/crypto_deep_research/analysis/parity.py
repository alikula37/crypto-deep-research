"""BTC/ETH parite analizi: oran trendi, tarihsel zirve ve direnç mesafesi."""

from __future__ import annotations

from crypto_deep_research.analysis.base import AnalysisContext, clamp, trend_score
from crypto_deep_research.analysis.indicators import compute_levels, ema, to_dataframe
from crypto_deep_research.models import AnalysisResult
from crypto_deep_research.providers.base import ProviderError, source


async def _pair_klines(ctx: AnalysisContext, pair_symbol: str):
    try:
        return await ctx.providers.exchange.klines(pair_symbol, "1d", 1000, quote=None)
    except ProviderError:
        return []


async def analyze_parity(ctx: AnalysisContext) -> AnalysisResult:
    symbol = ctx.coin.symbol.upper()
    sources = [
        source("Binance", "https://api.binance.com", note="parite serileri"),
        source("CoinGecko", "https://www.coingecko.com", note="dominance"),
    ]
    pair = None
    pair_label = None
    if symbol == "BTC":
        pair, pair_label = "ETHBTC", "ETH/BTC"
    elif symbol == "ETH":
        pair, pair_label = "ETHBTC", "ETH/BTC"
    else:
        pair, pair_label = f"{symbol}BTC", f"{symbol}/BTC"

    klines = await _pair_klines(ctx, pair)
    dominance = None
    try:
        global_market = await ctx.global_market()
        dominance = global_market.btc_dominance
    except Exception:
        pass

    if not klines and dominance is None:
        return ctx.result(
            "parity",
            "BTC/ETH Paritesi ve Direnç Mesafesi",
            status="no_data",
            summary=f"{symbol} için BTC paritesi verisi alınamadı.",
            sources=sources,
        )

    data: dict[str, object] = {"pair": pair_label, "btc_dominance": dominance}
    score = 0.0
    confidence = 0.2
    reasons: list[str] = []

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
                reasons.append(f"ETH/BTC düşüyor (%{change_30d:.1f}): sermaye BTC'ye kayiyor")
            elif change_30d is not None and change_30d > 3:
                score -= 0.4
                reasons.append(f"ETH/BTC yükseliyor (%{change_30d:.1f}): BTC'den ETH'e rotasyon")
        else:
            trend = trend_score(change_30d, 20.0)
            score += trend * 0.6
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

    if dominance is not None:
        confidence += 0.15
        data["btc_dominance"] = dominance
        if symbol == "BTC":
            if dominance > 55:
                score += 0.2
                reasons.append(f"BTC dominance %{dominance:.1f}: yüksek, BTC güçlü")
            elif dominance < 45:
                score -= 0.2
                reasons.append(f"BTC dominance %{dominance:.1f}: düşük, altcoin sezonu egilimi")
        else:
            if dominance > 58:
                score -= 0.2
                reasons.append(f"BTC dominance %{dominance:.1f}: altcoinler için baskı")
            elif dominance < 45:
                score += 0.2
                reasons.append(f"BTC dominance %{dominance:.1f}: altcoinlere sermaye akışı")

    summary = (
        f"{pair_label} güncel {data.get('ratio_now', 'n/a')}; "
        f"30g değişim %{data.get('ratio_change_30d_pct', 'n/a')}; "
        f"BTC dominance %{dominance:.1f}." if dominance else f"{pair_label} analizi yapıldı."
    )

    return ctx.result(
        "parity",
        "BTC/ETH Paritesi ve Direnç Mesafesi",
        summary=summary,
        data={"reasons": reasons, **data},
        sources=sources,
        score=round(clamp(score), 4),
        confidence=round(min(confidence, 1.0), 3),
    )
