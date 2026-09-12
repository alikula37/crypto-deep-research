"""Haber ve sentiment analizi: son haberler, duygu skorları, haber hızı."""

from __future__ import annotations

from collections import Counter
from datetime import timedelta

from crypto_deep_research.analysis.base import AnalysisContext, clamp
from crypto_deep_research.models import AnalysisResult
from crypto_deep_research.providers.base import source


async def analyze_news(ctx: AnalysisContext) -> AnalysisResult:
    articles = await ctx.articles(hours=72)
    sources = [
        source("CryptoPanic", "https://cryptopanic.com", note="haber + topluluk sentiment"),
        source("RSS (CoinDesk/Cointelegraph/Decrypt/The Block)", note="haber akışları", kind="rss"),
        source("GDELT", "https://api.gdeltproject.org", note="haber hacmi/jeopolitik"),
    ]
    if not articles:
        return ctx.result(
            "news",
            "Son Haberler ve Sentiment",
            status="no_data",
            summary="Haber kaynaklarına ulaşilamadi.",
            sources=sources,
        )

    try:
        volume_timeline = await ctx.providers.news.gdelt_volume(ctx.coin, hours=24)
    except Exception:
        volume_timeline = []

    sentiment_24h = ctx.providers.news.aggregate_sentiment(articles, hours=24)
    sentiment_72h = ctx.providers.news.aggregate_sentiment(articles, hours=72)
    now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)

    hourly = Counter()
    source_counter = Counter()
    for article in articles:
        source_counter[article.source] += 1
        if article.published_at:
            delta = now - article.published_at
            if delta <= timedelta(hours=48):
                hourly[int(delta.total_seconds() // 3600)] += 1

    velocity = {
        "last_6h": sum(count for hour, count in hourly.items() if hour < 6),
        "prev_6h": sum(count for hour, count in hourly.items() if 6 <= hour < 12),
        "last_24h": sum(count for hour, count in hourly.items() if hour < 24),
        "prev_24h": sum(count for hour, count in hourly.items() if 24 <= hour < 48),
    }
    velocity_ratio = (
        velocity["last_6h"] / velocity["prev_6h"] if velocity["prev_6h"] else None
    )

    ranked = sorted(
        articles,
        key=lambda a: (a.sentiment or 0.0) * (1.0 if a.published_at else 0.5),
    )
    negative = [
        {"title": a.title, "source": a.source, "url": a.url, "sentiment": a.sentiment}
        for a in ranked[:5]
    ]
    positive = [
        {"title": a.title, "source": a.source, "url": a.url, "sentiment": a.sentiment}
        for a in ranked[-5:][::-1]
    ]

    avg_sentiment = sentiment_24h["avg_sentiment"]
    score = clamp(avg_sentiment * 2.5)
    confidence = min(1.0, sentiment_24h["sample_size"] / 40) * 0.8
    reasons: list[str] = []

    if avg_sentiment > 0.15:
        reasons.append(f"24s haber sentiment pozitif ({avg_sentiment:.2f}): iyimserlik")
    elif avg_sentiment < -0.15:
        reasons.append(f"24s haber sentiment negatif ({avg_sentiment:.2f}): kötümserlik")
    else:
        reasons.append(f"24s haber sentiment nötr ({avg_sentiment:.2f})")

    if velocity_ratio is not None:
        if velocity_ratio > 1.5:
            reasons.append(
                f"Haber yazilma hızı arttı (son 6s önceki 6s'in {velocity_ratio:.1f}x): volatilite riski"
            )
        elif velocity_ratio < 0.5:
            reasons.append("Haber akışı yavaşladı: sakin dönem")

    channel_sentiment = {}
    for channel in ("Binance", "Coinbase", "ETF"):
        channel_articles = [a for a in articles if channel.lower() in a.title.lower()]
        if channel_articles:
            scores = [a.sentiment or 0 for a in channel_articles]
            channel_sentiment[channel] = round(sum(scores) / len(scores), 3)

    summary = (
        f"24s {sentiment_24h['sample_size']} haber incelendi; ortalama sentiment "
        f"{avg_sentiment:.2f} (pozitif {sentiment_24h['positive']}, negatif {sentiment_24h['negative']}). "
        f"72s ortalama: {sentiment_72h['avg_sentiment']:.2f}."
    )

    return ctx.result(
        "news",
        "Son Haberler ve Sentiment Skorları",
        summary=summary,
        data={
            "sentiment_24h": sentiment_24h,
            "sentiment_72h": sentiment_72h,
            "velocity": velocity,
            "velocity_ratio_6h": round(velocity_ratio, 3) if velocity_ratio else None,
            "top_positive": positive,
            "top_negative": negative,
            "article_count": len(articles),
            "source_distribution": dict(source_counter.most_common(12)),
            "gdelt_volume_points": len(volume_timeline),
            "channel_sentiment": channel_sentiment,
            "reasons": reasons,
        },
        sources=sources,
        score=round(score, 4),
        confidence=round(confidence, 3),
    )
