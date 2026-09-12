"""66 maddenin analiz edicileri: özel hesaplamalar, haber sorgulari ve analiz eslemeleri."""

from __future__ import annotations

import logging
import math
import re
from collections import Counter
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any

import numpy as np

from crypto_deep_research.analysis.base import AnalysisContext, clamp, trend_score
from crypto_deep_research.analysis.indicators import atr, to_dataframe
from crypto_deep_research.deep_research.registry import ItemSpec
from crypto_deep_research.formatting import money
from crypto_deep_research.formatting import pct as fmt_pct
from crypto_deep_research.formatting import price as fmt_price
from crypto_deep_research.models import AnalysisResult, ItemResult
from crypto_deep_research.providers.base import ProviderError, source

logger = logging.getLogger(__name__)

SpecialFn = Callable[
    [AnalysisContext, ItemSpec, dict[str, AnalysisResult]], Awaitable[ItemResult]
]


# ---------------------------------------------------------------------- yardımcilar
def result_from(
    spec: ItemSpec,
    *,
    status: str = "ok",
    summary: str = "",
    data: dict | None = None,
    sources: list | None = None,
    score: float | None = None,
    confidence: float = 0.0,
    warnings: list[str] | None = None,
) -> ItemResult:
    return ItemResult(
        item_id=spec.id,
        title_tr=spec.title_tr,
        description_tr=spec.description_tr,
        note=spec.note,
        category=spec.category,
        weight=spec.weight,
        qualitative=spec.source_type in ("news", "unavailable"),
        key=f"item_{spec.id}",
        title=spec.title_tr,
        status=status,  # type: ignore[arg-type]
        summary=summary,
        data=data or {},
        sources=sources or [],
        score=score,
        confidence=confidence,
        warnings=warnings or [],
    )


def get_analysis(analyses: dict[str, AnalysisResult], key: str) -> AnalysisResult | None:
    return analyses.get(key)


def _match_articles(articles: list, keywords: list[str]) -> list:
    matched = []
    for article in articles:
        haystack = f"{article.title} {article.summary or ''}".lower()
        if any(keyword.lower() in haystack for keyword in keywords):
            matched.append(article)
    return matched


def _sentiment_of(articles: list) -> tuple[float, int]:
    if not articles:
        return 0.0, 0
    scores = [article.sentiment or 0.0 for article in articles]
    return float(sum(scores) / len(scores)), len(scores)


async def _news_item(ctx: AnalysisContext, spec: ItemSpec) -> ItemResult:
    articles = await ctx.articles(hours=168)
    keywords = spec.keywords or [spec.query or spec.title_tr]
    matched = _match_articles(articles, keywords)
    if not articles:
        return result_from(
            spec,
            status="no_data",
            summary="Haber kaynaklarına ulaşilamadi.",
            score=None,
            confidence=0.0,
        )
    if not matched:
        return result_from(
            spec,
            status="partial",
            summary=f"Son 7 günde '{', '.join(keywords[:3])}' ile ilgili haber bulunamadı (nötr).",
            data={"query": spec.query, "matched": 0, "total_articles": len(articles)},
            sources=[
                source("RSS haber kaynakları", kind="rss"),
                source("GDELT", "https://api.gdeltproject.org", kind="api"),
            ],
            score=0.0,
            confidence=0.1,
        )
    avg_sentiment, count = _sentiment_of(matched)
    score = clamp(avg_sentiment * 2.0)
    confidence = min(0.8, 0.25 + count / 40)
    latest = sorted(matched, key=lambda a: a.published_at or datetime.now(timezone.utc), reverse=True)[:5]
    return result_from(
        spec,
        summary=(
            f"{count} ilgili haber bulundu; ortalama sentiment {avg_sentiment:.2f}."
        ),
        data={
            "query": spec.query,
            "keywords": keywords,
            "matched": count,
            "avg_sentiment": round(avg_sentiment, 4),
            "headlines": [
                {
                    "title": article.title,
                    "source": article.source,
                    "url": article.url,
                    "published_at": article.published_at.isoformat() if article.published_at else None,
                    "sentiment": article.sentiment,
                }
                for article in latest
            ],
        },
        sources=[
            source("RSS haber kaynakları", kind="rss"),
            source("CryptoPanic", "https://cryptopanic.com"),
            source("GDELT", "https://api.gdeltproject.org"),
        ],
        score=round(score, 4),
        confidence=round(confidence, 3),
    )


# ---------------------------------------------------------------------- special: temel
async def fundamentals(ctx: AnalysisContext, spec: ItemSpec, analyses: dict) -> ItemResult:
    snapshot = await ctx.snapshot()
    detail = await ctx.coin_detail()
    revenue = get_analysis(analyses, "revenue")
    circulating = snapshot.circulating_supply
    total = snapshot.total_supply
    max_supply = snapshot.max_supply
    fdv = snapshot.fully_diluted_valuation_usd
    mcap = snapshot.market_cap_usd

    score = 0.0
    confidence = 0.3
    reasons: list[str] = []
    data: dict[str, Any] = {
        "circulating_supply": circulating,
        "total_supply": total,
        "max_supply": max_supply,
        "fdv_usd": fdv,
        "fdv_over_mcap": round(fdv / mcap, 3) if (fdv and mcap) else None,
        "ath_change_pct": snapshot.ath_change_pct,
        "rank": snapshot.rank,
        "categories": detail.get("categories") or [],
        "has_public_description": bool((detail.get("description") or {}).get("en")),
    }
    if fdv and mcap:
        ratio = fdv / mcap
        if ratio < 1.2:
            score += 0.25
            reasons.append(f"FDV/mcap {ratio:.2f}: düşük seyreltme riski")
        elif ratio > 2:
            score -= 0.3
            reasons.append(f"FDV/mcap {ratio:.2f}: yüksek enflasyon/seyreltme riski")
        confidence += 0.15
    if circulating and total and total > 0:
        unlocked = circulating / total
        data["unlocked_pct"] = round(unlocked * 100, 2)
        if unlocked > 0.9:
            score += 0.15
            reasons.append("Dolaşımdaki arz toplam arzın %90+ (arz baskısı düşük)")
        elif unlocked < 0.5:
            score -= 0.2
            reasons.append("Toplam arzın yaridan azi dolaşımda: kilit acilma baskısı riski")
        confidence += 0.1
    if revenue and revenue.score is not None:
        score += revenue.score * 0.35
        confidence += 0.15
        reasons.append(f"Gelir analizi skoru {revenue.score:+.2f}")

    summary = (
        f"FDV/mcap {data.get('fdv_over_mcap')}; dolaşım %{data.get('unlocked_pct', 'n/a')}; "
        f"piyasa sıralaması #{snapshot.rank}."
    )
    return result_from(
        spec,
        summary=summary,
        data={"reasons": reasons, **data},
        sources=[
            source("CoinGecko", "https://www.coingecko.com"),
            source("DefiLlama", "https://defillama.com"),
        ],
        score=round(clamp(score), 4),
        confidence=round(min(confidence, 1.0), 3),
    )


async def market_sensitivity(ctx: AnalysisContext, spec: ItemSpec, analyses: dict) -> ItemResult:
    fng = await ctx.providers.sentiment.fear_greed(limit=7)
    liquidations = get_analysis(analyses, "liquidations")
    news = get_analysis(analyses, "news")
    score = 0.0
    confidence = 0.2
    reasons: list[str] = []
    data: dict[str, Any] = {}

    if fng:
        current = fng[0]
        data["fear_greed"] = current.model_dump(mode="json")
        confidence += 0.25
        if current.value <= 25:
            score += 0.35
            reasons.append(f"Korku endeksi {current.value}: aşırı korku, kontrarian fırsat")
        elif current.value >= 75:
            score -= 0.35
            reasons.append(f"Korku endeksi {current.value}: aşırı acgozluluk, düzeltme riski")
        if len(fng) > 3 and fng[0].value != fng[-1].value:
            data["fear_greed_trend"] = fng[0].value - fng[-1].value

    if liquidations and liquidations.score is not None:
        score += liquidations.score * 0.4
        confidence += 0.2
        reasons.append(f"Türev piyasa skoru {liquidations.score:+.2f}")
    if news and news.score is not None:
        score += news.score * 0.3
        confidence += 0.15
        reasons.append(f"Haber skoru {news.score:+.2f}")

    return result_from(
        spec,
        summary="Duyarlılık: " + ("; ".join(reasons[:3]) if reasons else "veri kısmi"),
        data={"reasons": reasons, **data},
        sources=[
            source("alternative.me Fear & Greed", "https://alternative.me/crypto/fear-and-greed-index/"),
            source("Binance Futures", "https://fapi.binance.com"),
        ],
        score=round(clamp(score), 4),
        confidence=round(min(confidence, 1.0), 3),
    )


async def investor_behavior(ctx: AnalysisContext, spec: ItemSpec, analyses: dict) -> ItemResult:
    score = 0.0
    confidence = 0.2
    reasons: list[str] = []
    data: dict[str, Any] = {}
    sources = [source("alternative.me", "https://alternative.me/crypto/fear-and-greed-index/")]
    fng = await ctx.providers.sentiment.fear_greed(limit=30)
    if fng:
        current = fng[0].value
        avg_30 = sum(item.value for item in fng) / len(fng)
        data.update({"fear_greed_current": current, "fear_greed_avg_30d": round(avg_30, 1)})
        confidence += 0.2
        if current > avg_30 + 10:
            score += 0.2
            reasons.append("Iyimserlik 30 gün ortalamasının üzerinde: momentum")
        elif current < avg_30 - 10:
            score -= 0.15
            reasons.append("Iyimserlik 30 gün ortalamasının altında")

    chain = ctx.coin.id
    if chain == "bitcoin":
        stats = await ctx.providers.onchain.btc_network_stats()
        sources.append(source("Blockchain.com", "https://api.blockchain.com"))
        if stats:
            confidence += 0.2
            addresses = stats.get("unique_addresses") or {}
            txs = stats.get("n_transactions") or {}
            data["btc_network"] = stats
            if addresses.get("change_pct") is not None:
                change = addresses["change_pct"]
                score += trend_score(change, 20.0) * 0.25
                reasons.append(f"Aktif adres değişimi %{change:.1f}")
            if txs.get("change_pct") is not None:
                reasons.append(f"İşlem sayısı değişimi %{txs['change_pct']:.1f}")
    elif chain == "ethereum":
        stats = await ctx.providers.onchain.eth_stats()
        sources.append(source("Blockscout", "https://eth.blockscout.com"))
        if stats:
            confidence += 0.2
            data["eth_network"] = {
                "total_addresses": stats.get("total_addresses"),
                "total_transactions": stats.get("total_transactions"),
                "transactions_today": stats.get("transactions_today"),
                "network_utilization": stats.get("network_utilization_percentage"),
            }
            reasons.append("ETH ag istatistikleri alındı")
    else:
        reasons.append("Bu varlık için ücretsiz ag aktivite verisi sınırlı")

    return result_from(
        spec,
        summary="Yatırımcı davranisi: " + ("; ".join(reasons[:3]) if reasons else "veri kısmi"),
        data={"reasons": reasons, **data},
        sources=sources,
        score=round(clamp(score), 4),
        confidence=round(min(confidence, 1.0), 3),
    )


async def sector(ctx: AnalysisContext, spec: ItemSpec, analyses: dict) -> ItemResult:
    categories = await ctx.providers.coingecko.categories(ctx.coin.id)
    all_categories = await ctx.providers.coingecko.coins_categories()
    match = None
    for category in categories:
        for entry in all_categories:
            if str(entry.get("name", "")).lower() == category.lower():
                match = entry
                break
        if match:
            break
    if not categories:
        return result_from(spec, status="no_data", summary="Sektör/kategori bilgisi bulunamadı.", confidence=0.0)
    if not match:
        return result_from(
            spec,
            status="partial",
            summary=f"Kategoriler: {', '.join(categories[:4])}. Kategori performans verisi bulunamadı.",
            data={"categories": categories},
            sources=[source("CoinGecko Categories", "https://www.coingecko.com/en/categories")],
            score=0.0,
            confidence=0.2,
        )
    change_24h = match.get("market_cap_change_24h")
    change_7d = match.get("market_cap_change_7d") if "market_cap_change_7d" in match else None
    score = clamp(trend_score(change_24h, 8.0) * 0.7 + trend_score(change_7d, 15.0) * 0.3)
    return result_from(
        spec,
        summary=(
            f"Sektör '{match.get('name')}': 24s mcap değişimi "
            f"{fmt_pct(change_24h, signed=True) if change_24h is not None else 'veri yok'}."
        ),
        data={
            "categories": categories,
            "sector_name": match.get("name"),
            "sector_market_cap_usd": match.get("market_cap"),
            "sector_change_24h_pct": change_24h,
            "sector_change_7d_pct": change_7d,
            "sector_volume_24h_usd": match.get("volume_24h"),
            "sector_top_coins": match.get("top_3_coins_id") or [],
        },
        sources=[source("CoinGecko Categories", "https://www.coingecko.com/en/categories")],
        score=round(score, 4),
        confidence=0.5,
    )


async def technology(ctx: AnalysisContext, spec: ItemSpec, analyses: dict) -> ItemResult:
    detail = await ctx.coin_detail()
    links = (detail.get("links") or {})
    repos = (links.get("repos_url") or {}).get("github") or []
    dev = detail.get("developer_data") or {}
    data: dict[str, Any] = {
        "github_repos": repos[:3],
        "stars": dev.get("stars"),
        "forks": dev.get("forks"),
        "subscribers": dev.get("subscribers"),
        "commit_count_4_weeks": dev.get("commit_count_4_weeks"),
        "closed_issues": dev.get("closed_issues"),
    }
    score = 0.0
    confidence = 0.2
    reasons: list[str] = []

    if repos:
        try:
            repo_url = repos[0].rstrip("/").replace("https://github.com/", "")
            repo_data = await ctx.providers.http.get_json(
                "github",
                f"https://api.github.com/repos/{repo_url}",
                ttl=3600,
            )
            data.update(
                {
                    "repo": repo_url,
                    "repo_stars": repo_data.get("stargazers_count"),
                    "repo_forks": repo_data.get("forks_count"),
                    "open_issues": repo_data.get("open_issues_count"),
                    "last_push": repo_data.get("pushed_at"),
                    "archived": repo_data.get("archived"),
                }
            )
            confidence += 0.3
            reasons.append(f"GitHub: {repo_data.get('stargazers_count')} yıldız, son push {str(repo_data.get('pushed_at'))[:10]}")
            if repo_data.get("archived"):
                score -= 0.4
                reasons.append("Depo arşivlenmis: geliştirme durmus")
        except ProviderError:
            reasons.append("GitHub verisi alınamadı")
    if dev.get("commit_count_4_weeks"):
        commits = float(dev["commit_count_4_weeks"])
        if commits > 30:
            score += 0.3
            reasons.append(f"Son 4 haftada {commits:.0f} commit: aktif geliştirme")
        elif commits < 5:
            score -= 0.2
            reasons.append("Son 4 haftada az commit")

    if not repos and not dev:
        return result_from(
            spec,
            status="partial",
            summary="Teknoloji verisi sınırlı (GitHub/dokumantasyon bağlantısı yok).",
            data=data,
            sources=[source("CoinGecko", "https://www.coingecko.com"), source("GitHub", "https://api.github.com")],
            score=0.0,
            confidence=0.15,
        )
    return result_from(
        spec,
        summary="Teknoloji: " + "; ".join(reasons[:3]),
        data={"reasons": reasons, **data},
        sources=[source("GitHub API", "https://api.github.com"), source("CoinGecko", "https://www.coingecko.com")],
        score=round(clamp(score), 4),
        confidence=round(min(confidence, 1.0), 3),
    )


# ---------------------------------------------------------------------- special: teknik
async def tradingview_proxy(ctx: AnalysisContext, spec: ItemSpec, analyses: dict) -> ItemResult:
    technical = get_analysis(analyses, "technical")
    if not technical or technical.status == "error":
        return result_from(spec, status="no_data", summary="Teknik veri yok.", confidence=0.0)
    score = technical.score or 0.0
    if score > 0.45:
        rating = "Güçlü Alis"
    elif score > 0.15:
        rating = "Alis"
    elif score < -0.45:
        rating = "Güçlü Satış"
    elif score < -0.15:
        rating = "Satış"
    else:
        rating = "Nötr"
    data = {
        "rating": rating,
        "score": score,
        "method": "Yerel indikatör topluluğu (TradingView derecelendirme vekili)",
    }
    indicators = (technical.data or {}).get("indicators") or {}
    data["key_indicators"] = {
        key: indicators.get(key)
        for key in ("rsi_14", "macd_histogram", "ema_50", "ema_200", "stoch_k")
    }
    return result_from(
        spec,
        summary=f"Teknik derecelendirme vekili: {rating} (skor {score:+.2f}).",
        data=data,
        sources=[source("Yerel hesaplama (TradingView vekili)", kind="computed")],
        score=round(score, 4),
        confidence=round(min(0.6, technical.confidence), 3),
        warnings=["TradingView resmi API'si ücretsiz olmadığı için yerel derecelendirme kullanıldı."],
    )


async def fractal(ctx: AnalysisContext, spec: ItemSpec, analyses: dict) -> ItemResult:
    klines = await ctx.klines(500)
    if len(klines) < 120:
        return result_from(spec, status="no_data", summary="Fraktal analiz için veri yetersiz.", confidence=0.0)
    df = to_dataframe(klines)
    log_returns = np.log(df["close"] / df["close"].shift(1)).dropna().values
    if len(log_returns) < 100:
        return result_from(spec, status="no_data", summary="Getiri serisi yetersiz.", confidence=0.0)
    lags = [2, 4, 8, 16, 32]
    variances = []
    for lag in lags:
        aggregated = np.add.reduceat(log_returns, np.arange(0, len(log_returns) - lag, lag))
        variances.append(max(float(np.var(aggregated)), 1e-12))
    slopes = np.polyfit(np.log(lags), np.log(variances), 1)
    beta = float(slopes[0])
    hurst = beta / 2.0
    trend_30d = float(df["close"].iloc[-1] / df["close"].iloc[-31] - 1) * 100 if len(df) > 31 else 0.0
    score = 0.0
    reasons: list[str] = []
    if hurst > 0.58:
        score = clamp(trend_30d / 20.0) * 0.7
        regime = "trend rejimi (persistent)"
        reasons.append(f"Hurst {hurst:.2f}: trend devam egilimi")
    elif hurst < 0.42:
        score = -clamp(trend_30d / 20.0) * 0.5
        regime = "ortalamaya dönüş rejimi"
        reasons.append(f"Hurst {hurst:.2f}: ortalamaya dönüş egilimi")
    else:
        regime = "rastgele yuruyus"
        reasons.append(f"Hurst {hurst:.2f}: belirgin rejim yok")
    return result_from(
        spec,
        summary=f"Fraktal: {regime}; Hurst={hurst:.3f}, 30g trend %{trend_30d:.1f}.",
        data={
            "hurst_exponent": round(hurst, 4),
            "beta": round(beta, 4),
            "regime": regime,
            "trend_30d_pct": round(trend_30d, 2),
            "reasons": reasons,
        },
        sources=[source("Yerel hesaplama (R/S analizi)", kind="computed")],
        score=round(clamp(score), 4),
        confidence=0.5,
    )


async def psych_levels(ctx: AnalysisContext, spec: ItemSpec, analyses: dict) -> ItemResult:
    snapshot = await ctx.snapshot()
    price = snapshot.price_usd
    magnitude = 10 ** math.floor(math.log10(price)) if price > 0 else 1
    round_levels = []
    for factor in (0.5, 1, 2, 5, 10):
        level = round(price / (magnitude * factor / 10)) * (magnitude * factor / 10)
        round_levels.append(level)
    round_levels = sorted({level for level in round_levels if level > 0})
    above = [level for level in round_levels if level >= price]
    below = [level for level in round_levels if level < price]
    nearest_resistance = min(above) if above else None
    nearest_support = max(below) if below else None
    distance_resistance = (nearest_resistance / price - 1) * 100 if nearest_resistance else None
    distance_support = (price / nearest_support - 1) * 100 if nearest_support else None

    score = 0.0
    reasons: list[str] = []
    if distance_resistance is not None and distance_resistance < 1.0:
        score -= 0.2
        reasons.append(
            f"Yuvarlak sayı direnci {fmt_price(nearest_resistance)} çok yakın "
            f"(mesafe {fmt_pct(distance_resistance)})"
        )
    if distance_support is not None and distance_support < 1.0:
        score += 0.15
        reasons.append(f"Yuvarlak sayı desteği {fmt_price(nearest_support)} çok yakın")
    if distance_resistance is not None and 1.0 <= distance_resistance < 3:
        score += 0.1
        reasons.append("Yuvarlak direnç kırılirsa hızlı hareket potansiyeli")

    return result_from(
        spec,
        summary=(
            f"Psikolojik seviyeler: destek {fmt_price(nearest_support)}, "
            f"direnç {fmt_price(nearest_resistance)}."
        ),
        data={
            "nearest_support": nearest_support,
            "nearest_resistance": nearest_resistance,
            "distance_to_support_pct": round(distance_support, 2) if distance_support is not None else None,
            "distance_to_resistance_pct": round(distance_resistance, 2) if distance_resistance is not None else None,
            "levels": round_levels,
            "reasons": reasons,
        },
        sources=[source("Yerel hesaplama (yuvarlak sayılar)", kind="computed")],
        score=round(clamp(score), 4),
        confidence=0.4,
    )


# ---------------------------------------------------------------------- special: kantitatif
async def historical_similarity(ctx: AnalysisContext, spec: ItemSpec, analyses: dict) -> ItemResult:
    klines = await ctx.klines(1000)
    if len(klines) < 120:
        return result_from(spec, status="no_data", summary="Tarihsel benzerlik için veri yetersiz.", confidence=0.0)
    df = to_dataframe(klines)
    closes = df["close"].values
    returns = np.diff(np.log(closes))
    window = 20
    if len(returns) < window + 40:
        return result_from(spec, status="no_data", summary="Getiri serisi kısa.", confidence=0.0)
    current = returns[-window:]
    candidates: list[tuple[float, float]] = []
    for end in range(window, len(returns) - 10):
        past = returns[end - window : end]
        distance = float(np.linalg.norm(past - current))
        forward_10 = float(closes[end + 10] / closes[end] - 1) * 100 if end + 10 < len(closes) else 0.0
        candidates.append((distance, forward_10))
    candidates.sort(key=lambda item: item[0])
    top = candidates[: min(8, len(candidates))]
    forward_returns = [item[1] for item in top]
    avg_forward = float(np.mean(forward_returns)) if forward_returns else 0.0
    positive_ratio = sum(1 for value in forward_returns if value > 0) / len(forward_returns) if forward_returns else 0
    score = clamp(avg_forward / 6.0) * 0.7 + (positive_ratio - 0.5) * 0.6
    return result_from(
        spec,
        summary=(
            f"En benzer {len(top)} tarihsel pencerede 10 günlük ortalama getiri %{avg_forward:.2f} "
            f"(pozitif oran %{positive_ratio * 100:.0f})."
        ),
        data={
            "matched_windows": len(top),
            "avg_forward_return_10d_pct": round(avg_forward, 2),
            "positive_ratio": round(positive_ratio, 3),
            "forward_returns": [round(value, 2) for value in forward_returns],
            "method": "20 günlük log-getiri vektörü, Oklid mesafesi",
        },
        sources=[source("Yerel hesaplama (tarihsel benzerlik)", kind="computed")],
        score=round(clamp(score), 4),
        confidence=0.45,
    )


async def seasonality(ctx: AnalysisContext, spec: ItemSpec, analyses: dict) -> ItemResult:
    chart = await ctx.providers.coingecko.market_chart(ctx.coin.id, days=365)
    prices = [float(pair[1]) for pair in chart.get("prices") or [] if pair and pair[1]]
    if len(prices) < 90:
        klines = await ctx.klines(500)
        prices = [kline.close for kline in klines]
    if len(prices) < 90:
        return result_from(spec, status="no_data", summary="Mevsimsellik için veri yetersiz.", confidence=0.0)
    now = datetime.now(timezone.utc)
    monthly: dict[int, list[float]] = {}
    daily_returns = []
    for index in range(1, len(prices)):
        daily_returns.append(prices[index] / prices[index - 1] - 1)
    step = max(1, len(daily_returns) // 365)
    for index in range(1, len(prices)):
        date = now - __import__("datetime").timedelta(days=(len(prices) - index) * step)
        monthly.setdefault(date.month, []).append(daily_returns[index - 1])
    month_returns = {month: sum(values) / len(values) * 100 for month, values in monthly.items() if values}
    current_month_return = month_returns.get(now.month)
    weekday_returns: dict[int, list[float]] = {}
    for index in range(1, len(prices)):
        date = now - __import__("datetime").timedelta(days=(len(prices) - index) * step)
        weekday_returns.setdefault(date.weekday(), []).append(daily_returns[index - 1])
    weekday_avg = {day: sum(values) / len(values) * 100 for day, values in weekday_returns.items() if values}
    score = clamp((current_month_return or 0) / 4.0) * 0.6
    return result_from(
        spec,
        summary=(
            f"{now.strftime('%B')} ayi tarihsel ortalama günlük getirisi "
            f"%{current_month_return:.3f}." if current_month_return is not None else "Aylık veri yok."
        ),
        data={
            "current_month": now.month,
            "monthly_avg_daily_return_pct": {month: round(value, 4) for month, value in sorted(month_returns.items())},
            "weekday_avg_daily_return_pct": {day: round(value, 4) for day, value in sorted(weekday_avg.items())},
            "method": "Günlük getirilerin ay/gün bazlı ortalaması",
        },
        sources=[source("CoinGecko", "https://www.coingecko.com"), source("Yerel hesaplama", kind="computed")],
        score=round(clamp(score), 4),
        confidence=0.3,
        warnings=["Mevsimsellik zayıf bir istatistiksel sinyaldır; tek başına kullanılmamalıdır."],
    )


async def regression_trend(ctx: AnalysisContext, spec: ItemSpec, analyses: dict) -> ItemResult:
    klines = await ctx.klines(365)
    if len(klines) < 60:
        return result_from(spec, status="no_data", summary="Regresyon için veri yetersiz.", confidence=0.0)
    df = to_dataframe(klines)
    y = np.log(df["close"].tail(90).values)
    x = np.arange(len(y))
    slope, intercept = np.polyfit(x, y, 1)
    predicted = slope * x + intercept
    ss_res = float(np.sum((y - predicted) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    r_squared = 1 - ss_res / ss_tot if ss_tot else 0.0
    daily_growth = (math.exp(slope) - 1) * 100
    score = clamp(daily_growth / 0.5) * (0.5 + 0.5 * max(0.0, r_squared))
    return result_from(
        spec,
        summary=(
            f"90 günlük log-lineer trend: günlük %{daily_growth:.3f} (R2={r_squared:.2f})."
        ),
        data={
            "daily_growth_pct": round(daily_growth, 4),
            "annualized_growth_pct": round(((1 + daily_growth / 100) ** 365 - 1) * 100, 2),
            "r_squared": round(r_squared, 4),
            "slope": round(float(slope), 6),
        },
        sources=[source("Yerel hesaplama (log-lineer regresyon)", kind="computed")],
        score=round(clamp(score), 4),
        confidence=round(0.3 + 0.4 * max(0.0, r_squared), 3),
    )


async def volatility_model(ctx: AnalysisContext, spec: ItemSpec, analyses: dict) -> ItemResult:
    klines = await ctx.klines(400)
    if len(klines) < 60:
        return result_from(spec, status="no_data", summary="Volatilite modeli için veri yetersiz.", confidence=0.0)
    df = to_dataframe(klines)
    returns = np.diff(np.log(df["close"].values))
    lam = 0.94
    ewma_var = float(np.var(returns))
    for value in returns:
        ewma_var = lam * ewma_var + (1 - lam) * value * value
    current_vol = math.sqrt(ewma_var) * 100
    rolling = []
    window = 30
    for index in range(window, len(returns)):
        rolling.append(float(np.std(returns[index - window : index])) * 100)
    percentile = (
        sum(1 for value in rolling if value <= current_vol) / len(rolling) if rolling else None
    )
    atr_series = atr(df)
    atr_pct = float(atr_series.iloc[-1] / df["close"].iloc[-1] * 100)
    score = 0.0
    if percentile is not None and percentile > 0.9:
        score = 0.15
    elif percentile is not None and percentile < 0.1:
        score = 0.0
    return result_from(
        spec,
        summary=(
            f"EWMA volatilite %{current_vol:.2f}; 30g dagilim yüzdeliği "
            f"{'%' + str(round((percentile or 0) * 100)) if percentile is not None else 'veri yok'}; "
            f"ATR {fmt_pct(atr_pct)}."
        ),
        data={
            "ewma_vol_daily_pct": round(current_vol, 4),
            "volatility_percentile": round(percentile, 4) if percentile is not None else None,
            "atr_pct": round(atr_pct, 4),
            "method": "EWMA(lambda=0.94) + ATR(14)",
        },
        sources=[source("Yerel hesaplama (EWMA/GARCH yaklaşımi)", kind="computed")],
        score=round(clamp(score), 4),
        confidence=0.45,
        warnings=["Deneysel model; yatırım kararı için tek başına kullanılmamalıdır."],
    )


async def pipeline_meta(ctx: AnalysisContext, spec: ItemSpec, analyses: dict) -> ItemResult:
    ok_count = sum(1 for result in analyses.values() if result.status == "ok")
    partial_count = sum(1 for result in analyses.values() if result.status == "partial")
    error_count = sum(1 for result in analyses.values() if result.status == "error")
    source_names = sorted({s.name for result in analyses.values() for s in result.sources})
    quality = ok_count / max(len(analyses), 1)
    return result_from(
        spec,
        summary=(
            f"Veri hatti: {ok_count} tam, {partial_count} kısmi, {error_count} hatalı analiz; "
            f"{len(source_names)} farkli kaynak."
        ),
        data={
            "analyses_ok": ok_count,
            "analyses_partial": partial_count,
            "analyses_error": error_count,
            "sources": source_names,
            "quality_ratio": round(quality, 3),
        },
        sources=[source("Pipeline metrigi", kind="computed")],
        score=0.0,
        confidence=0.2,
    )


# ---------------------------------------------------------------------- special: makro
async def _macro_data(ctx: AnalysisContext) -> dict[str, dict[str, Any]]:
    if "macro_data" not in ctx.extra:
        ctx.extra["macro_data"] = await ctx.providers.macro.market_data(period="6mo")
    return ctx.extra["macro_data"]


async def macro(ctx: AnalysisContext, spec: ItemSpec, analyses: dict) -> ItemResult:
    data = await _macro_data(ctx)
    if not data:
        return result_from(
            spec,
            status="partial",
            summary="yfinance verisi alınamadı; makro tablo sınırlı.",
            sources=[source("yfinance", "https://finance.yahoo.com")],
            score=0.0,
            confidence=0.1,
        )
    score = 0.0
    reasons: list[str] = []
    dxy = data.get("DXY")
    spx = data.get("SPX")
    us10y = data.get("US10Y")
    if dxy and dxy.get("change_30d_pct") is not None:
        if dxy["change_30d_pct"] < -1:
            score += 0.35
            reasons.append(f"DXY 30g %{dxy['change_30d_pct']:.1f}: dolar zayıf, risk varlıklarına pozitif")
        elif dxy["change_30d_pct"] > 1:
            score -= 0.35
            reasons.append(f"DXY 30g %{dxy['change_30d_pct']:.1f}: dolar güçlü, risk varlıklarına negatif")
    if spx and spx.get("change_30d_pct") is not None:
        if spx["change_30d_pct"] > 2:
            score += 0.25
            reasons.append(f"S&P 500 30g %{spx['change_30d_pct']:.1f}: risk istahi yüksek")
        elif spx["change_30d_pct"] < -2:
            score -= 0.25
            reasons.append(f"S&P 500 30g %{spx['change_30d_pct']:.1f}: risk istahi düşük")
    if us10y and us10y.get("change_30d_pct") is not None and us10y["change_30d_pct"] > 5:
        score -= 0.15
        reasons.append("ABD 10Y getirisi yükseliyor: likidite baskısı")

    return result_from(
        spec,
        summary="Makro: " + ("; ".join(reasons[:3]) if reasons else "nötr görünüm"),
        data={"reasons": reasons, "macro": data},
        sources=[source("yfinance", "https://finance.yahoo.com")],
        score=round(clamp(score), 4),
        confidence=0.55,
    )


async def alternatives(ctx: AnalysisContext, spec: ItemSpec, analyses: dict) -> ItemResult:
    data = await _macro_data(ctx)
    if not data:
        return result_from(spec, status="partial", summary="Alternatif varlık verisi yok.", confidence=0.1)
    returns = {
        label: data.get(label, {}).get("change_30d_pct")
        for label in ("GOLD", "SILVER", "OIL", "SPX", "NASDAQ")
    }
    available = {key: value for key, value in returns.items() if value is not None}
    avg = sum(available.values()) / len(available) if available else 0.0
    score = clamp(avg / 15.0) * 0.5
    return result_from(
        spec,
        summary=f"Alternatif varlıkların 30g ortalama getirisi %{avg:.2f}.",
        data={"returns_30d_pct": returns, "average_30d_pct": round(avg, 2)},
        sources=[source("yfinance", "https://finance.yahoo.com")],
        score=round(clamp(score), 4),
        confidence=0.4,
    )


async def correlation(ctx: AnalysisContext, spec: ItemSpec, analyses: dict) -> ItemResult:
    macro_data = await _macro_data(ctx)
    klines = await _daily_closes(ctx)
    if not klines:
        return result_from(spec, status="no_data", summary="Korelasyon için fiyat serisi yok.", confidence=0.0)
    coin_returns = np.diff(np.log(np.array(klines)))
    correlations: dict[str, float | None] = {}
    for label in ("SPX", "NASDAQ", "GOLD", "DXY", "VIX", "US10Y"):
        series = (macro_data.get(label) or {}).get("series") or []
        if len(series) < 30:
            correlations[label] = None
            continue
        macro_returns = np.diff(np.log(np.array(series, dtype=float)))
        length = min(len(coin_returns), len(macro_returns))
        if length < 20:
            correlations[label] = None
            continue
        a = coin_returns[-length:]
        b = macro_returns[-length:]
        if np.std(a) == 0 or np.std(b) == 0:
            correlations[label] = None
            continue
        correlations[label] = round(float(np.corrcoef(a, b)[0, 1]), 3)

    score = 0.0
    reasons: list[str] = []
    dxy_corr = correlations.get("DXY")
    if dxy_corr is not None:
        score -= dxy_corr * 0.3
        reasons.append(f"DXY korelasyonu {dxy_corr:+.2f}")
    spx_corr = correlations.get("SPX")
    if spx_corr is not None:
        score += spx_corr * 0.25
        reasons.append(f"S&P korelasyonu {spx_corr:+.2f}")
    vix_corr = correlations.get("VIX")
    if vix_corr is not None:
        score -= vix_corr * 0.2

    return result_from(
        spec,
        summary="Korelasyon: " + ("; ".join(reasons) if reasons else "hesaplanamadi"),
        data={"correlations_90d": correlations, "reasons": reasons},
        sources=[source("yfinance", "https://finance.yahoo.com"), source("Yerel hesaplama", kind="computed")],
        score=round(clamp(score), 4),
        confidence=0.5,
    )


async def volatility_indices(ctx: AnalysisContext, spec: ItemSpec, analyses: dict) -> ItemResult:
    macro_data = await _macro_data(ctx)
    vix = (macro_data.get("VIX") or {}).get("latest")
    vix_change = (macro_data.get("VIX") or {}).get("change_7d_pct")
    dvol = None
    if ctx.coin.symbol.upper() in ("BTC", "ETH"):
        dvol = await ctx.providers.exchange.deribit_dvol(ctx.coin.symbol.upper())
    technical = get_analysis(analyses, "technical")
    atr_pct = ((technical.data or {}).get("indicators") or {}).get("atr_pct") if technical else None

    score = 0.0
    reasons: list[str] = []
    if vix is not None:
        if vix > 25:
            score -= 0.35
            reasons.append(f"VIX {vix:.1f}: yüksek korku, risk-off")
        elif vix < 15:
            score += 0.2
            reasons.append(f"VIX {vix:.1f}: düşük oynaklık, risk-on")
    if vix_change is not None and vix_change > 15:
        score -= 0.2
        reasons.append(f"VIX 7 günde %{vix_change:.0f} arttı: stres artışı")
    if dvol:
        reasons.append(f"Deribit DVOL (BTC) {dvol['current']:.1f}, 7g değişim {dvol['change_7d']:+.1f}")

    return result_from(
        spec,
        summary="Volatilite: " + ("; ".join(reasons[:3]) if reasons else "veri kısmi"),
        data={
            "vix": vix,
            "vix_change_7d_pct": vix_change,
            "deribit_dvol": dvol,
            "coin_atr_pct": atr_pct,
            "reasons": reasons,
        },
        sources=[
            source("yfinance VIX", "https://finance.yahoo.com/quote/%5EVIX"),
            source("Deribit DVOL", "https://www.deribit.com"),
        ],
        score=round(clamp(score), 4),
        confidence=0.5,
    )


async def macro_risk(ctx: AnalysisContext, spec: ItemSpec, analyses: dict) -> ItemResult:
    macro_data = await _macro_data(ctx)
    vix = (macro_data.get("VIX") or {}).get("latest")
    dxy_change = (macro_data.get("DXY") or {}).get("change_30d_pct")
    fred = await ctx.providers.macro.fred_dashboard()
    score = 0.0
    reasons: list[str] = []
    if vix is not None:
        if vix > 28:
            score -= 0.4
            reasons.append(f"VIX {vix:.1f}: makro stres yüksek")
        elif vix < 16:
            score += 0.2
            reasons.append(f"VIX {vix:.1f}: makro stres düşük")
    if dxy_change is not None:
        score -= clamp(dxy_change / 4.0) * 0.2
        reasons.append(f"DXY 30g %{dxy_change:+.1f}")
    if fred.get("T10Y2Y"):
        value = fred["T10Y2Y"]["latest"]
        reasons.append(f"10Y-2Y egrisi {value:+.2f}")
        if value < 0:
            score -= 0.1
    return result_from(
        spec,
        summary="Makro risk: " + ("; ".join(reasons[:3]) if reasons else "nötr"),
        data={"vix": vix, "dxy_change_30d_pct": dxy_change, "fred": fred, "reasons": reasons},
        sources=[
            source("yfinance", "https://finance.yahoo.com"),
            source("FRED", "https://fred.stlouisfed.org"),
        ],
        score=round(clamp(score), 4),
        confidence=0.55,
    )


async def capital_flows(ctx: AnalysisContext, spec: ItemSpec, analyses: dict) -> ItemResult:
    whales = get_analysis(analyses, "whales")
    macro_data = await _macro_data(ctx)
    articles = await ctx.articles(hours=72)
    etf_articles = _match_articles(articles, ["etf", "inflow", "outflow", "flow"])
    etf_sentiment, etf_count = _sentiment_of(etf_articles)
    score = 0.0
    reasons: list[str] = []
    data: dict[str, Any] = {"etf_article_count": etf_count, "etf_sentiment": round(etf_sentiment, 3)}
    if whales and whales.data.get("stablecoin_change_7d_pct") is not None:
        change = whales.data["stablecoin_change_7d_pct"]
        score += clamp(change / 3.0) * 0.35
        reasons.append(f"Stablecoin arzı 7g %{change:+.2f}%")
        data["stablecoin_change_7d_pct"] = change
    dxy_change = (macro_data.get("DXY") or {}).get("change_30d_pct")
    if dxy_change is not None:
        score -= clamp(dxy_change / 4.0) * 0.25
        reasons.append(f"DXY 30g %{dxy_change:+.1f}")
    if etf_count:
        score += clamp(etf_sentiment * 2.0) * 0.3
        reasons.append(f"ETF haber sentiment {etf_sentiment:+.2f} ({etf_count} haber)")
    return result_from(
        spec,
        summary="Sermaye akışları: " + ("; ".join(reasons[:3]) if reasons else "veri kısmi"),
        data={"reasons": reasons, **data},
        sources=[
            source("DefiLlama Stablecoins", "https://defillama.com/stablecoins"),
            source("yfinance", "https://finance.yahoo.com"),
            source("Haber RSS", kind="rss"),
        ],
        score=round(clamp(score), 4),
        confidence=0.5,
    )


async def stablecoin_flows(ctx: AnalysisContext, spec: ItemSpec, analyses: dict) -> ItemResult:
    charts = await ctx.providers.defillama.stablecoin_charts_all()
    if not charts:
        return result_from(spec, status="partial", summary="Stablecoin verisi alınamadı.", confidence=0.1)
    latest = charts[-1].get("totalCirculatingUSD") or {}
    total_now = sum(float(v) for v in latest.values()) if isinstance(latest, dict) else float(latest)
    changes = {}
    for days, label in ((1, "1d"), (7, "7d"), (30, "30d")):
        index = len(charts) - days - 1
        if index >= 0:
            past = charts[index].get("totalCirculatingUSD") or {}
            past_total = sum(float(v) for v in past.values()) if isinstance(past, dict) else float(past)
            changes[label] = round((total_now / past_total - 1) * 100, 3) if past_total else None
    change_7d = changes.get("7d")
    score = clamp((change_7d or 0) / 3.0) * 0.6
    reasons = []
    if change_7d is not None:
        direction = "girişi" if change_7d > 0 else "çıkışı"
        reasons.append(f"Stablecoin arzında 7 günde %{change_7d:+.2f} (piyasaya nakit {direction})")
    return result_from(
        spec,
        summary=(
            f"Stablecoin toplam arzı {money(total_now)}; 7 günlük değişim "
            f"{fmt_pct(change_7d, signed=True) if change_7d is not None else 'veri yok'}."
        ),
        data={
            "stablecoin_total_usd": total_now,
            "changes_pct": changes,
            "reasons": reasons,
        },
        sources=[source("DefiLlama Stablecoins", "https://defillama.com/stablecoins")],
        score=round(clamp(score), 4),
        confidence=0.55,
    )


# ---------------------------------------------------------------------- special: zincir-üstü
async def anomalies(ctx: AnalysisContext, spec: ItemSpec, analyses: dict) -> ItemResult:
    data: dict[str, Any] = {}
    reasons: list[str] = []
    score = 0.0
    sources = []
    my_chain = ctx.coin.id
    if my_chain == "bitcoin":
        fees = await ctx.providers.onchain.mempool_fees()
        stats = await ctx.providers.onchain.blockchain_chart("mempool_size")
        blockchair = await ctx.providers.onchain.blockchair_stats("bitcoin")
        sources.append(source("mempool.space", "https://mempool.space"))
        sources.append(source("Blockchair", "https://blockchair.com"))
        if fees:
            data["mempool_fees"] = fees
            if fees.get("fastestFee", 0) > 100:
                score -= 0.2
                reasons.append(f"Mempool ücretleri çok yüksek ({fees.get('fastestFee')} sat/vB): ag tikali")
        if stats:
            values = [float(point.get("y") or 0) for point in stats]
            if values:
                current = values[-1]
                percentile = sum(1 for value in values if value <= current) / len(values)
                data["mempool_size_percentile"] = round(percentile, 3)
                if percentile > 0.95:
                    score -= 0.15
                    reasons.append("Mempool boyutu tarihsel olarak çok yüksek: yoğunluk anomalisi")
        if blockchair:
            data["blockchair"] = {
                "blocks": blockchair.get("blocks"),
                "mempool_transactions": blockchair.get("mempool_transactions"),
                "market_price_usd": blockchair.get("market_price_usd"),
                "hashrate_24h": blockchair.get("hashrate_24h"),
            }
    elif my_chain == "ethereum":
        stats = await ctx.providers.onchain.eth_stats()
        gas = await ctx.providers.onchain.etherscan_gas()
        sources.append(source("Blockscout", "https://eth.blockscout.com"))
        if stats:
            data["eth_stats"] = {
                "gas_used_today": stats.get("gas_used_today"),
                "network_utilization": stats.get("network_utilization_percentage"),
                "transactions_today": stats.get("transactions_today"),
            }
            utilization = stats.get("network_utilization_percentage")
            if utilization and float(utilization) > 95:
                score -= 0.1
                reasons.append("Ag kullanımi %95+: yoğunluk")
        if gas:
            data["gas_oracle"] = gas
            if gas.get("ProposeGasPrice") and float(gas["ProposeGasPrice"]) > 50:
                score -= 0.15
                reasons.append("ETH gas ücretleri yüksek: ag yoğun")
    else:
        reasons.append("Bu varlık için ücretsiz zincir-üstü anomali verisi sınırlı")

    return result_from(
        spec,
        status="ok" if data else "partial",
        summary="Anomali taraması: " + ("; ".join(reasons[:3]) if reasons else "belirgin anomali yok"),
        data={"reasons": reasons, **data},
        sources=sources or [source("Zincir üstü gezginler", kind="page")],
        score=round(clamp(score), 4),
        confidence=0.4 if data else 0.15,
    )


async def wallet_growth(ctx: AnalysisContext, spec: ItemSpec, analyses: dict) -> ItemResult:
    data: dict[str, Any] = {}
    score = 0.0
    reasons: list[str] = []
    sources = []
    if ctx.coin.id == "bitcoin":
        values = await ctx.providers.onchain.blockchain_chart("unique_addresses", "90days")
        sources.append(source("Blockchain.com", "https://www.blockchain.com/charts"))
        if values:
            series = [float(point.get("y") or 0) for point in values]
            if len(series) >= 14:
                recent = sum(series[-7:]) / 7
                baseline = sum(series[:7]) / 7
                change = (recent / baseline - 1) * 100 if baseline else 0
                data.update(
                    {
                        "unique_addresses_latest": series[-1],
                        "change_90d_pct": round(change, 2),
                        "series_points": len(series),
                    }
                )
                score = clamp(change / 30.0) * 0.5
                reasons.append(f"Yeni adres oluşumu 90 günlük dönemde %{change:+.1f} değişti")
    elif ctx.coin.id == "ethereum":
        stats = await ctx.providers.onchain.eth_stats()
        sources.append(source("Blockscout", "https://eth.blockscout.com"))
        if stats:
            data.update(
                {
                    "total_addresses": stats.get("total_addresses"),
                    "total_transactions": stats.get("total_transactions"),
                }
            )
            reasons.append(
                f"Toplam ETH adresi {stats.get('total_addresses')} (büyüme oranı için geçmiş kosulara ihtiyaç var)"
            )
    else:
        return result_from(
            spec,
            status="no_data",
            summary="Cüzdan büyüme verisi yalnızca BTC/ETH için ücretsiz mevcut.",
            confidence=0.05,
            warnings=["Diger coinler için ücretsiz adres büyüme API'si bulunmuyor."],
        )

    if not data:
        return result_from(spec, status="partial", summary="Cüzdan verisi alınamadı.", confidence=0.1)
    return result_from(
        spec,
        summary="Cüzdan büyümesi: " + ("; ".join(reasons[:2]) if reasons else "veri kısmi"),
        data={"reasons": reasons, **data},
        sources=sources,
        score=round(clamp(score), 4),
        confidence=0.45 if ctx.coin.id == "bitcoin" else 0.25,
    )


async def mining_energy(ctx: AnalysisContext, spec: ItemSpec, analyses: dict) -> ItemResult:
    data: dict[str, Any] = {}
    score = 0.0
    reasons: list[str] = []
    sources = []
    if ctx.coin.id in ("bitcoin", "ethereum"):
        chart_key = "hash_rate" if ctx.coin.id == "bitcoin" else None
        if chart_key:
            stats = await ctx.providers.onchain.btc_network_stats()
            hashrate = (stats.get("hash_rate") or {})
            miners_revenue = (stats.get("miners_revenue_usd") or {})
            data.update({"hash_rate": hashrate, "miners_revenue": miners_revenue})
            sources.append(source("Blockchain.com", "https://www.blockchain.com/charts"))
            if hashrate.get("change_pct") is not None:
                change = hashrate["change_pct"]
                reasons.append(f"Hashrate 30g %{change:+.1f}")
                score += clamp(change / 30.0) * 0.3
            if miners_revenue.get("change_pct") is not None:
                reasons.append(f"Madenci geliri 30g %{miners_revenue['change_pct']:+.1f}")
        hashrate_data = await ctx.providers.onchain.mempool_hashrate()
        if hashrate_data:
            data["mempool_hashrate"] = {
                "currentHashrate": hashrate_data.get("currentHashrate"),
                "currentDifficulty": hashrate_data.get("currentDifficulty"),
            }
            sources.append(source("mempool.space", "https://mempool.space/mining"))
    macro_data = await _macro_data(ctx)
    oil = (macro_data.get("OIL") or {})
    if oil:
        data["oil_price"] = oil.get("latest")
        data["oil_change_30d_pct"] = oil.get("change_30d_pct")
        reasons.append(f"Petrol 30g %{oil.get('change_30d_pct', 0):+.1f}")
        score += clamp(-(oil.get("change_30d_pct") or 0) / 30.0) * 0.15
        sources.append(source("yfinance (petrol)", "https://finance.yahoo.com"))
    if not data:
        return result_from(spec, status="no_data", summary="Madencilik/enerji verisi yok.", confidence=0.05)
    return result_from(
        spec,
        summary="Madencilik/enerji: " + ("; ".join(reasons[:3]) if reasons else "veri kısmi"),
        data={"reasons": reasons, **data},
        sources=sources,
        score=round(clamp(score), 4),
        confidence=0.4,
    )


async def mining_shift(ctx: AnalysisContext, spec: ItemSpec, analyses: dict) -> ItemResult:
    base = await mining_energy(ctx, spec, analyses)
    articles = await ctx.articles(hours=168)
    matched = _match_articles(articles, ["mining", "miner", "hashrate", "madencilik"])
    news_sentiment, count = _sentiment_of(matched)
    base.data["mining_news_count"] = count
    base.data["mining_news_sentiment"] = round(news_sentiment, 3)
    base.score = clamp((base.score or 0.0) + news_sentiment * 0.3)
    base.summary += f" Ilgili haber: {count} (sentiment {news_sentiment:+.2f})."
    if count:
        base.sources.append(source("Haber RSS", kind="rss"))
        base.confidence = min(1.0, base.confidence + 0.1)
    return base


async def smart_contracts(ctx: AnalysisContext, spec: ItemSpec, analyses: dict) -> ItemResult:
    protocol = await ctx.providers.defillama.protocol(ctx.coin.id)
    articles = await ctx.articles(hours=168)
    exploit_articles = _match_articles(articles, ["exploit", "hack", "vulnerability", "audit", "bug"])
    exploit_sentiment, count = _sentiment_of(exploit_articles)
    data: dict[str, Any] = {"exploit_news_count": count, "exploit_sentiment": round(exploit_sentiment, 3)}
    score = clamp(exploit_sentiment * 0.8)
    confidence = 0.25
    reasons: list[str] = []
    if protocol:
        tvl = None
        try:
            if isinstance(protocol, list) and protocol:
                tvl = float(sum(float(chain.get("tvl") or 0) for chain in protocol[-1:] if isinstance(chain, dict)))
            elif isinstance(protocol, dict):
                tvl = protocol.get("tvl")
        except Exception:
            tvl = None
        data["protocol_tvl"] = tvl
        confidence += 0.25
    if count:
        confidence += 0.2
        reasons.append(f"{count} güvenlik/denetim haberi, sentiment {exploit_sentiment:+.2f}")
        if exploit_sentiment < -0.2:
            reasons.append("Güvenlik haberleri negatif: teknoloji riski")
    if not protocol and not count:
        return result_from(spec, status="partial", summary="Akıllı kontrat verisi sınırlı.", confidence=0.1)
    return result_from(
        spec,
        summary="Akıllı kontratlar: " + ("; ".join(reasons) if reasons else "belirgin risk sinyali yok"),
        data={"reasons": reasons, **data},
        sources=[
            source("DefiLlama", "https://defillama.com"),
            source("Haber RSS", kind="rss"),
        ],
        score=round(clamp(score), 4),
        confidence=round(min(confidence, 1.0), 3),
    )


async def cross_chain(ctx: AnalysisContext, spec: ItemSpec, analyses: dict) -> ItemResult:
    bridges = await ctx.providers.defillama.bridges()
    if not bridges:
        return result_from(spec, status="partial", summary="Bridge verisi alınamadı.", confidence=0.1)
    volumes = []
    for bridge in bridges:
        volume = bridge.get("last24hVolume") or bridge.get("volumePrevDay")
        if volume:
            volumes.append((bridge.get("displayName") or bridge.get("name"), float(volume)))
    volumes.sort(key=lambda item: item[1], reverse=True)
    total = sum(value for _, value in volumes)
    return result_from(
        spec,
        summary=f"Cross-chain: 24s köprü hacmi ~{money(total)} ({len(volumes)} köprü).",
        data={
            "total_bridge_volume_24h_usd": total,
            "top_bridges": [
                {"name": name, "volume_24h_usd": round(value, 2)} for name, value in volumes[:8]
            ],
        },
        sources=[source("DefiLlama Bridges", "https://defillama.com/bridges")],
        score=0.0,
        confidence=0.35,
    )


# ---------------------------------------------------------------------- special: sentiment
async def sentiment_combo(ctx: AnalysisContext, spec: ItemSpec, analyses: dict) -> ItemResult:
    news = get_analysis(analyses, "news")
    await ctx.articles(hours=48)
    reddit = await ctx.providers.sentiment.reddit(ctx.coin, limit=50)
    reddit_stats = ctx.providers.sentiment.reddit_sentiment(reddit, ctx.providers.news._analyzer)
    score = 0.0
    confidence = 0.15
    reasons: list[str] = []
    data: dict[str, Any] = {"reddit": reddit_stats}
    if news and news.data.get("sentiment_24h"):
        news_sentiment = news.data["sentiment_24h"]["avg_sentiment"]
        score += clamp(news_sentiment * 2.0) * 0.5
        confidence += 0.3
        reasons.append(f"Haber sentiment {news_sentiment:+.2f}")
    if reddit_stats["sample_size"]:
        score += clamp(reddit_stats["avg_sentiment"] * 2.0) * 0.3
        confidence += 0.2
        reasons.append(f"Reddit sentiment {reddit_stats['avg_sentiment']:+.2f} ({reddit_stats['sample_size']} gonderi)")
    fng = await ctx.providers.sentiment.fear_greed(limit=1)
    if fng:
        value = fng[0].value
        data["fear_greed"] = value
        confidence += 0.15
        score += (50 - value) / 100 * 0.4
        reasons.append(f"Fear & Greed {value} ({fng[0].classification})")
    if not reasons:
        return result_from(spec, status="no_data", summary="Sentiment verisi yok.", confidence=0.05)
    return result_from(
        spec,
        summary="Duygu analizi: " + "; ".join(reasons[:3]),
        data={"reasons": reasons, **data},
        sources=[
            source("Haber RSS + CryptoPanic", kind="rss"),
            source("Reddit", "https://www.reddit.com"),
            source("alternative.me", "https://alternative.me/crypto/fear-and-greed-index/"),
        ],
        score=round(clamp(score), 4),
        confidence=round(min(confidence, 1.0), 3),
    )


async def crowd_psychology(ctx: AnalysisContext, spec: ItemSpec, analyses: dict) -> ItemResult:
    fng = await ctx.providers.sentiment.fear_greed(limit=30)
    liquidations = get_analysis(analyses, "liquidations")
    score = 0.0
    confidence = 0.15
    reasons: list[str] = []
    data: dict[str, Any] = {}
    if fng:
        current = fng[0]
        avg = sum(item.value for item in fng) / len(fng)
        data.update({"fear_greed": current.value, "fear_greed_avg_30d": round(avg, 1)})
        confidence += 0.3
        if current.value < 20:
            score += 0.45
            reasons.append(f"Aşırı korku ({current.value}): kalabalik satiyor, kontrarian pozitif")
        elif current.value < 40:
            score += 0.15
            reasons.append(f"Korku bölgesi ({current.value})")
        elif current.value > 80:
            score -= 0.45
            reasons.append(f"Aşırı acgozluluk ({current.value}): kalabalik aliyor, risk yüksek")
        elif current.value > 60:
            score -= 0.15
            reasons.append(f"Acgozluluk bölgesi ({current.value})")
        if current.value > avg + 15:
            score -= 0.15
            reasons.append("Duygu 30 gün ortalamasının çok üzerinde: aşırı iyimserlik")
        elif current.value < avg - 15:
            score += 0.15
            reasons.append("Duygu 30 gün ortalamasının çok altında: aşırı kötümserlik")
    if liquidations and liquidations.data.get("long_short_ratio"):
        ratio = liquidations.data["long_short_ratio"]
        data["long_short_ratio"] = ratio
        confidence += 0.15
        if ratio > 2:
            score -= 0.2
            reasons.append("Long/short oranı aşırı long: kalabalik aynı yönde")
        elif ratio < 0.8:
            score += 0.2
            reasons.append("Long/short oranı aşırı short: kalabalik aynı yönde")
    if not reasons:
        return result_from(spec, status="partial", summary="Kitle psikolojisi verisi kısmi.", confidence=0.15)
    return result_from(
        spec,
        summary="Kitle psikolojisi: " + "; ".join(reasons[:3]),
        data={"reasons": reasons, **data},
        sources=[
            source("alternative.me", "https://alternative.me/crypto/fear-and-greed-index/"),
            source("Binance Futures", "https://fapi.binance.com"),
        ],
        score=round(clamp(score), 4),
        confidence=round(min(confidence, 1.0), 3),
    )


async def news_velocity(ctx: AnalysisContext, spec: ItemSpec, analyses: dict) -> ItemResult:
    news = get_analysis(analyses, "news")
    if not news or not news.data.get("velocity"):
        return result_from(spec, status="partial", summary="Haber hızı verisi yok.", confidence=0.1)
    velocity = news.data["velocity"]
    ratio = news.data.get("velocity_ratio_6h")
    score = 0.0
    if ratio is not None:
        if ratio > 2:
            score = -0.2
        elif ratio < 0.5:
            score = 0.1
    return result_from(
        spec,
        summary=(
            f"Haber hızı: son 6s {velocity.get('last_6h')} haber, önceki 6s {velocity.get('prev_6h')} "
            f"(oran {ratio if ratio is not None else '—'})."
        ),
        data={"velocity": velocity, "velocity_ratio_6h": ratio},
        sources=[source("GDELT", "https://api.gdeltproject.org"), source("Haber RSS", kind="rss")],
        score=round(clamp(score), 4),
        confidence=0.4,
    )


async def google_trends(ctx: AnalysisContext, spec: ItemSpec, analyses: dict) -> ItemResult:
    trends = await ctx.providers.sentiment.google_trends(ctx.coin)
    if not trends:
        return result_from(
            spec,
            status="partial",
            summary="Google Trends verisi alınamadı (servis limiti).",
            confidence=0.05,
        )
    change = trends.get("change_vs_baseline_pct") or 0
    score = clamp(change / 50.0) * 0.4
    direction = "arttı" if change > 0 else "azaldı"
    return result_from(
        spec,
        summary=f"Arama ilgisi 7 günlük ortalamada %{change:+.1f} {direction}.",
        data=trends,
        sources=[source("Google Trends", "https://trends.google.com")],
        score=round(clamp(score), 4),
        confidence=0.35,
    )


async def media_manipulation(ctx: AnalysisContext, spec: ItemSpec, analyses: dict) -> ItemResult:
    articles = await ctx.articles(hours=48)
    if not articles:
        return result_from(spec, status="partial", summary="Haber verisi yok.", confidence=0.05)
    normalized = [re.sub(r"[^a-z0-9 ]", "", article.title.lower()) for article in articles]
    titles = Counter(normalized)
    duplicates = sum(count - 1 for count in titles.values() if count > 1)
    duplicate_ratio = duplicates / len(articles)
    sentiments = [article.sentiment or 0.0 for article in articles]
    dispersion = float(np.std(sentiments)) if sentiments else 0.0
    score = 0.0
    warnings: list[str] = []
    if duplicate_ratio > 0.15:
        warnings.append(
            f"Aynı haber {duplicates} kez farkli kaynaklarda tekrarlanmis: bilgi kirliligi/manipülasyon olabilir"
        )
    if dispersion > 0.45:
        warnings.append("Haber sentiment dagilimi çok genis: celiskili anlatilar")
    return result_from(
        spec,
        summary=(
            f"Medya analizi: {len(articles)} haber, tekrar oranı %{duplicate_ratio * 100:.1f}, "
            f"sentiment sapması {dispersion:.2f}."
        ),
        data={
            "article_count": len(articles),
            "duplicate_ratio": round(duplicate_ratio, 3),
            "sentiment_dispersion": round(dispersion, 3),
        },
        sources=[source("Haber RSS", kind="rss"), source("CryptoPanic", "https://cryptopanic.com")],
        score=score,
        confidence=0.35,
        warnings=warnings,
    )


# ---------------------------------------------------------------------- special: piyasa
async def composite(ctx: AnalysisContext, spec: ItemSpec, analyses: dict) -> ItemResult:
    scores = [
        (key, result.score, result.confidence)
        for key, result in analyses.items()
        if result.score is not None and result.confidence > 0
    ]
    if not scores:
        return result_from(spec, status="no_data", summary="Sentetik kıyaslama için skor yok.", confidence=0.0)
    weighted = sum(score * confidence for _, score, confidence in scores)
    total_weight = sum(confidence for _, _, confidence in scores)
    composite_score = weighted / total_weight if total_weight else 0.0
    bullish = [key for key, score, confidence in scores if score > 0.15 and confidence > 0.3]
    bearish = [key for key, score, confidence in scores if score < -0.15 and confidence > 0.3]
    return result_from(
        spec,
        summary=(
            f"Sentetik skor {composite_score:+.3f}; {len(bullish)} analiz pozitif, {len(bearish)} negatif."
        ),
        data={
            "composite_score": round(composite_score, 4),
            "components": {key: round(score, 3) for key, score, _ in scores},
            "bullish_components": bullish,
            "bearish_components": bearish,
        },
        sources=[source("Sentetik kıyaslama (pipeline)", kind="computed")],
        score=round(clamp(composite_score), 4),
        confidence=0.6,
    )


async def offchain(ctx: AnalysisContext, spec: ItemSpec, analyses: dict) -> ItemResult:
    volumes = get_analysis(analyses, "volumes")
    liquidations = get_analysis(analyses, "liquidations")
    score = 0.0
    confidence = 0.2
    reasons: list[str] = []
    data: dict[str, Any] = {}
    if volumes and volumes.score is not None:
        score += volumes.score * 0.5
        confidence += 0.25
        reasons.append(f"Hacim skoru {volumes.score:+.2f}")
        data["turnover_ratio"] = (volumes.data or {}).get("turnover_ratio")
    if liquidations and liquidations.score is not None:
        score += liquidations.score * 0.5
        confidence += 0.25
        reasons.append(f"Türev skoru {liquidations.score:+.2f}")
        data["funding_annualized_pct"] = (liquidations.data or {}).get("funding_annualized_pct")
    if not reasons:
        return result_from(spec, status="partial", summary="Off-chain veri kısmi.", confidence=0.1)
    return result_from(
        spec,
        summary="Off-chain veriler: " + "; ".join(reasons),
        data={"reasons": reasons, **data},
        sources=[
            source("Binance Futures", "https://fapi.binance.com"),
            source("CoinGecko", "https://www.coingecko.com"),
        ],
        score=round(clamp(score), 4),
        confidence=round(min(confidence, 1.0), 3),
    )


async def sell_pressure(ctx: AnalysisContext, spec: ItemSpec, analyses: dict) -> ItemResult:
    order_book = None
    try:
        order_book = await ctx.providers.exchange.binance_order_book(ctx.coin.symbol, limit=500)
    except ProviderError:
        order_book = None
    news = get_analysis(analyses, "news")
    liquidations = get_analysis(analyses, "liquidations")
    score = 0.0
    confidence = 0.15
    reasons: list[str] = []
    data: dict[str, Any] = {}
    if order_book:
        bids = sum(float(price) * float(qty) for price, qty in order_book.get("bids") or [])
        asks = sum(float(price) * float(qty) for price, qty in order_book.get("asks") or [])
        total = bids + asks
        imbalance = (bids - asks) / total if total else 0
        data["order_book_imbalance"] = round(imbalance, 4)
        data["bid_depth_usd"] = round(bids, 2)
        data["ask_depth_usd"] = round(asks, 2)
        confidence += 0.3
        if imbalance < -0.15:
            score -= 0.4
            reasons.append("Satış tarafi derinligi baskın: satış baskısı")
        elif imbalance > 0.15:
            score += 0.4
            reasons.append("Alis tarafi derinligi baskın: alım baskısı")
    if liquidations and liquidations.data.get("liquidations_long_usd_48h"):
        long_liq = liquidations.data["liquidations_long_usd_48h"]
        short_liq = liquidations.data.get("liquidations_short_usd_48h") or 0
        if long_liq + short_liq > 0:
            long_share = long_liq / (long_liq + short_liq)
            data["long_liquidation_share"] = round(long_share, 3)
            confidence += 0.2
            if long_share > 0.65:
                score -= 0.35
                reasons.append("Likidasyonların çoğu long: satış baskısı")
            elif long_share < 0.35:
                score += 0.35
                reasons.append("Likidasyonların çoğu short: alım baskısı")
    if news and news.data.get("sentiment_24h"):
        sentiment = news.data["sentiment_24h"]["avg_sentiment"]
        if sentiment < -0.2:
            score -= 0.2
            reasons.append(f"Negatif haber sentiment {sentiment:.2f}")
            confidence += 0.15
        elif sentiment > 0.2:
            score += 0.2
            confidence += 0.15
    if not reasons:
        return result_from(spec, status="partial", summary="Satış baskısı sinyali kısmi.", confidence=0.1)
    return result_from(
        spec,
        summary="Satış baskısı: " + "; ".join(reasons[:3]),
        data={"reasons": reasons, **data},
        sources=[
            source("Binance order book", "https://api.binance.com"),
            source("Coinalyze", "https://coinalyze.net"),
            source("Haber RSS", kind="rss"),
        ],
        score=round(clamp(score), 4),
        confidence=round(min(confidence, 1.0), 3),
    )


async def dominance(ctx: AnalysisContext, spec: ItemSpec, analyses: dict) -> ItemResult:
    global_market = await ctx.global_market()
    btc = global_market.btc_dominance
    eth = global_market.eth_dominance
    if btc is None:
        return result_from(spec, status="partial", summary="Dominance verisi yok.", confidence=0.1)
    score = 0.0
    reasons: list[str] = []
    symbol = ctx.coin.symbol.upper()
    if symbol == "BTC":
        score = clamp((btc - 50) / 15.0) * 0.4
        reasons.append(f"BTC dominance %{btc:.1f}")
    elif symbol == "ETH":
        score = clamp((eth - 10) / 8.0) * 0.3
        reasons.append(f"ETH dominance %{eth:.1f}")
    else:
        score = clamp((45 - btc) / 12.0) * 0.4
        reasons.append(f"BTC dominance %{btc:.1f}: " + ("altcoinler için elverisli" if btc < 50 else "BTC baskın"))
    change = global_market.market_cap_change_24h_pct
    if change is not None:
        score += clamp(change / 5.0) * 0.2
        reasons.append(f"Toplam mcap 24s %{change:+.1f}")
    return result_from(
        spec,
        summary=f"Bitcoin dominance %{btc:.1f}; ETH %{eth:.1f}. " + "; ".join(reasons[1:]),
        data={
            "btc_dominance": btc,
            "eth_dominance": eth,
            "total_market_cap_usd": global_market.total_market_cap_usd,
            "market_cap_change_24h_pct": change,
            "reasons": reasons,
        },
        sources=[source("CoinGecko Global", "https://www.coingecko.com/en/global-charts")],
        score=round(clamp(score), 4),
        confidence=0.5,
    )


async def energy_costs(ctx: AnalysisContext, spec: ItemSpec, analyses: dict) -> ItemResult:
    macro_data = await _macro_data(ctx)
    oil = macro_data.get("OIL") or {}
    gas = macro_data.get("GAS") or macro_data.get("COPPER") or {}
    score = 0.0
    reasons: list[str] = []
    if oil:
        change = oil.get("change_30d_pct")
        reasons.append(f"Petrol 30g {fmt_pct(change, signed=True) if change is not None else 'veri yok'}")
        if change is not None:
            score += clamp(-change / 30.0) * 0.25
    mining = await mining_energy(ctx, spec, analyses)
    combined = (score + (mining.score or 0.0)) / 2
    data = {
        "oil_price": oil.get("latest"),
        "oil_change_30d_pct": oil.get("change_30d_pct"),
        "gas_related": gas,
        "mining_data": mining.data,
        "reasons": reasons + (mining.data.get("reasons") or []),
    }
    return result_from(
        spec,
        summary="Enerji maliyetleri: " + ("; ".join(data["reasons"][:3]) if data["reasons"] else "veri kısmi"),
        data=data,
        sources=mining.sources + [source("yfinance (enerji)", "https://finance.yahoo.com")],
        score=round(clamp(combined), 4),
        confidence=round((mining.confidence + 0.4) / 2, 3),
    )


# ---------------------------------------------------------------------- kayıt defteri
def _daily_closes(ctx: AnalysisContext) -> Awaitable[list[float]]:
    async def _load() -> list[float]:
        klines = await ctx.providers.exchange.klines(ctx.coin.symbol, "1d", 200)
        return [kline.close for kline in klines]

    return _load()


SPECIALS: dict[str, SpecialFn] = {
    "fundamentals": fundamentals,
    "market_sensitivity": market_sensitivity,
    "investor_behavior": investor_behavior,
    "sector": sector,
    "technology": technology,
    "tradingview_proxy": tradingview_proxy,
    "fractal": fractal,
    "psych_levels": psych_levels,
    "historical_similarity": historical_similarity,
    "seasonality": seasonality,
    "regression_trend": regression_trend,
    "volatility_model": volatility_model,
    "pipeline_meta": pipeline_meta,
    "macro": macro,
    "alternatives": alternatives,
    "correlation": correlation,
    "volatility_indices": volatility_indices,
    "macro_risk": macro_risk,
    "capital_flows": capital_flows,
    "stablecoin_flows": stablecoin_flows,
    "anomalies": anomalies,
    "wallet_growth": wallet_growth,
    "mining_energy": mining_energy,
    "mining_shift": mining_shift,
    "smart_contracts": smart_contracts,
    "cross_chain": cross_chain,
    "sentiment_combo": sentiment_combo,
    "crowd_psychology": crowd_psychology,
    "news_velocity": news_velocity,
    "google_trends": google_trends,
    "media_manipulation": media_manipulation,
    "composite": composite,
    "offchain": offchain,
    "sell_pressure": sell_pressure,
    "dominance": dominance,
    "energy_costs": energy_costs,
}


async def evaluate_item(
    ctx: AnalysisContext, spec: ItemSpec, analyses: dict[str, AnalysisResult]
) -> ItemResult:
    """Bir maddeyi kaynağına göre değerlendirir."""
    if spec.source_type == "analysis" and spec.source_ref:
        analysis = analyses.get(spec.source_ref)
        if analysis is None:
            return result_from(spec, status="no_data", summary="Ilgili analiz sonuçu bulunamadı.", confidence=0.0)
        summary = analysis.summary
        if spec.id in (14, 15, 16, 19) and analysis.data:
            if spec.id == 14:
                patterns = analysis.data.get("candle_patterns") or []
                summary = "Mum formasyonları: " + (", ".join(patterns) if patterns else "belirgin formasyon yok")
            elif spec.id == 15:
                patterns = analysis.data.get("chart_patterns") or []
                summary = "Grafik formasyonları: " + (", ".join(patterns) if patterns else "belirgin formasyon yok")
            elif spec.id == 16:
                fib = (analysis.data.get("levels") or {}).get("fibonacci") or {}
                summary = "Fibonacci seviyeleri: " + ", ".join(
                    f"{key}={fmt_price(value)}" for key, value in list(fib.items())[:6]
                )
            elif spec.id == 19:
                levels = analysis.data.get("levels") or {}
                supports = ", ".join(fmt_price(v) for v in (levels.get("support") or [])[:3])
                resistances = ", ".join(fmt_price(v) for v in (levels.get("resistance") or [])[:3])
                summary = f"Destekler: {supports or '—'} | Dirençler: {resistances or '—'}"
        return result_from(
            spec,
            status=analysis.status,
            summary=summary,
            data=analysis.data,
            sources=analysis.sources,
            score=analysis.score,
            confidence=analysis.confidence,
            warnings=analysis.warnings,
        )
    if spec.source_type == "special" and spec.source_ref:
        fn = SPECIALS.get(spec.source_ref)
        if fn is None:
            return result_from(spec, status="error", summary=f"Bilinmeyen özel analiz: {spec.source_ref}")
        try:
            return await fn(ctx, spec, analyses)
        except ProviderError as exc:
            return result_from(spec, status="partial", summary=f"Veri kaynağı hatası: {exc}", confidence=0.05)
        except Exception as exc:  # savunmaci: tek madde tüm kosuyu bozmasin
            logger.exception("Madde %s değerlendirilemedi", spec.id)
            return result_from(
                spec,
                status="error",
                summary=f"Değerlendirme hatası: {exc}",
                confidence=0.0,
                warnings=["Bu madde hata verdi; ağırlıklı ortalamada dikkate alınmadı."],
            )
    if spec.source_type == "news":
        try:
            return await _news_item(ctx, spec)
        except Exception as exc:
            logger.exception("Haber maddesi %s değerlendirilemedi", spec.id)
            return result_from(spec, status="error", summary=f"Haber değerlendirme hatası: {exc}", confidence=0.0)
    return result_from(
        spec,
        status="no_data",
        summary=(
            spec.note
            or "Bu madde için ücretsiz ve doğrulanabilir veri kaynağı bulunmuyor; nötr kabul edildi."
        ),
        confidence=0.0,
        warnings=["Veri yok: ağırlıklı ortalamaya dahil edilmedi."],
    )
