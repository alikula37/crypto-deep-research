"""Sentiment sağlayıcıları: Fear & Greed, Reddit, Google Trends."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from crypto_deep_research.config import Settings
from crypto_deep_research.models import CoinRef, FearGreed
from crypto_deep_research.providers.base import CachedHTTP, ProviderError

logger = logging.getLogger(__name__)

FNG = "https://api.alternative.me/fng/"
REDDIT = "https://www.reddit.com"


class SentimentProvider:
    name = "sentiment"

    def __init__(self, http: CachedHTTP, settings: Settings) -> None:
        self.http = http
        self.settings = settings

    # ------------------------------------------------------------------ Fear & Greed
    async def fear_greed(self, limit: int = 30) -> list[FearGreed]:
        try:
            data = await self.http.get_json(
                "alternative_me",
                FNG,
                params={"limit": limit, "format": "json"},
                ttl=self.settings.ttl_sentiment,
            )
        except ProviderError:
            return []
        out: list[FearGreed] = []
        for item in (data or {}).get("data") or []:
            try:
                out.append(
                    FearGreed(
                        value=int(item["value"]),
                        classification=item.get("value_classification") or "",
                        timestamp=datetime.fromtimestamp(int(item["timestamp"]), tz=timezone.utc),
                    )
                )
            except (KeyError, ValueError, TypeError):
                continue
        return out

    # ------------------------------------------------------------------ Reddit
    async def reddit(self, coin: CoinRef, limit: int = 50) -> list[dict[str, Any]]:
        subreddits = {
            "bitcoin": "bitcoin",
            "ethereum": "ethereum",
            "solana": "solana",
        }.get(coin.id, "cryptocurrency")
        headers = {"User-Agent": "crypto-deep-research/0.1 by alikula37"}
        try:
            data = await self.http.get_json(
                "reddit",
                f"{REDDIT}/r/{subreddits}/new.json",
                params={"limit": limit},
                headers=headers,
                ttl=self.settings.ttl_sentiment,
            )
        except ProviderError:
            return []
        posts: list[dict[str, Any]] = []
        for child in ((data or {}).get("data") or {}).get("children") or []:
            post = child.get("data") or {}
            posts.append(
                {
                    "title": post.get("title") or "",
                    "score": post.get("score") or 0,
                    "num_comments": post.get("num_comments") or 0,
                    "created_utc": post.get("created_utc"),
                    "url": f"https://reddit.com{post.get('permalink', '')}",
                    "subreddit": post.get("subreddit"),
                }
            )
        return posts

    # ------------------------------------------------------------------ Google Trends
    async def google_trends(self, coin: CoinRef, timeframe: str = "today 3-m") -> dict[str, Any] | None:
        """pytrends ile arama ilgisi; servis limitlerinde None donebilir."""
        def _fetch() -> dict[str, Any] | None:
            try:
                from pytrends.request import TrendReq

                pytrends = TrendReq(hl="en-US", tz=0, timeout=(10, 25))
                terms = [coin.name, f"{coin.name} price"]
                pytrends.build_payload(terms, timeframe=timeframe)
                frame = pytrends.interest_over_time()
                if frame is None or frame.empty:
                    return None
                series = frame[coin.name].tolist()
                recent = series[-7:] if len(series) >= 7 else series
                baseline = series[-90:] if len(series) >= 30 else series
                return {
                    "current": float(series[-1]),
                    "avg_recent_7": float(sum(recent) / len(recent)),
                    "avg_baseline": float(sum(baseline) / len(baseline)),
                    "max_90d": float(max(baseline)),
                    "change_vs_baseline_pct": round(
                        (sum(recent) / len(recent)) / max(sum(baseline) / len(baseline), 1) * 100 - 100,
                        2,
                    ),
                    "source": "Google Trends (pytrends)",
                }
            except Exception as exc:  # pytrends servis hatalarina karsi savunmaci
                logger.info("Google Trends alınamadı: %s", exc)
                return None

        result = await asyncio.to_thread(_fetch)
        if result:
            self.settings.data_dir.mkdir(parents=True, exist_ok=True)
        return result

    @staticmethod
    def reddit_sentiment(posts: list[dict[str, Any]], analyzer: Any) -> dict[str, Any]:
        if not posts:
            return {"avg_sentiment": 0.0, "sample_size": 0, "avg_score": 0.0}
        scores = [float(analyzer.polarity_scores(p["title"])["compound"]) for p in posts]
        return {
            "avg_sentiment": round(sum(scores) / len(scores), 4),
            "sample_size": len(scores),
            "avg_score": round(sum(p.get("score", 0) for p in posts) / len(posts), 2),
            "avg_comments": round(
                sum(p.get("num_comments", 0) for p in posts) / len(posts), 2
            ),
        }
