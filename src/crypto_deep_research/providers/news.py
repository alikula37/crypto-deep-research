"""Haber sağlayıcıları: CryptoPanic, RSS kaynakları ve GDELT + VADER sentiment."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import feedparser
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from crypto_deep_research.config import Settings
from crypto_deep_research.models import CoinRef, NewsArticle, utcnow
from crypto_deep_research.providers.base import CachedHTTP, ProviderError
from crypto_deep_research.storage.db import Database

logger = logging.getLogger(__name__)

CRYPTOPANIC = "https://cryptopanic.com/api/v1/posts/"

RSS_FEEDS: list[tuple[str, str]] = [
    ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("Cointelegraph", "https://cointelegraph.com/rss"),
    ("Cointelegraph TR", "https://tr.cointelegraph.com/rss"),
    ("Decrypt", "https://decrypt.co/feed"),
    ("The Block", "https://www.theblock.co/rss.xml"),
    ("Bitcoin Magazine", "https://bitcoinmagazine.com/.rss/full/"),
    ("CryptoSlate", "https://cryptoslate.com/feed/"),
    ("BeInCrypto", "https://beincrypto.com/feed/"),
    ("CoinJournal", "https://coinjournal.net/feed/"),
]

GDELT_DOC = "https://api.gdeltproject.org/api/v2/doc/doc"
GOOGLE_NEWS = "https://news.google.com/rss/search"


def build_topic_query(keywords: list[str], max_terms: int = 4) -> str:
    """GDELT icin OR'lu sorgu uretir: '("kw1" OR "kw2" OR ...)'."""
    terms = []
    seen: set[str] = set()
    for keyword in keywords:
        term = (keyword or "").strip().replace('"', "")
        if len(term) < 3 or term.lower() in seen:
            continue
        seen.add(term.lower())
        terms.append(term)
        if len(terms) >= max_terms:
            break
    if not terms:
        return ""
    return "(" + " OR ".join(f'"{term}"' for term in terms) + ")"

_CRYPTO_LEXICON: dict[str, float] = {
    "bullish": 2.8,
    "bearish": -2.8,
    "rally": 2.0,
    "surge": 2.2,
    "soar": 2.4,
    "crash": -2.8,
    "plunge": -2.4,
    "dump": -2.0,
    "hack": -3.0,
    "exploit": -2.8,
    "etf approval": 2.8,
    "etf inflow": 2.2,
    "etf outflow": -2.2,
    "halving": 1.5,
    "adoption": 1.8,
    "ban": -2.6,
    "lawsuit": -1.8,
    "sec sues": -2.4,
    "all-time high": 2.6,
    "record high": 2.4,
    "liquidation": -1.6,
    "bankruptcy": -3.0,
    "partnership": 1.6,
    "upgrade": 1.4,
    "downgrade": -1.6,
}


class NewsProvider:
    """Çoklu kaynaktan haber toplar, sentiment hesaplar ve önbelleğe yazar."""

    name = "news"

    def __init__(
        self, http: CachedHTTP, db: Database, settings: Settings
    ) -> None:
        self.http = http
        self.db = db
        self.settings = settings
        self._analyzer = SentimentIntensityAnalyzer()
        self._analyzer.lexicon.update(_CRYPTO_LEXICON)

    # ------------------------------------------------------------------ sentiment
    def score_text(self, text: str) -> float:
        if not text:
            return 0.0
        return float(self._analyzer.polarity_scores(text)["compound"])

    def score_article(self, article: NewsArticle) -> NewsArticle:
        if article.sentiment_raw is not None:
            article.sentiment = article.sentiment_raw
            return article
        text = f"{article.title}. {article.summary or ''}"
        article.sentiment = self.score_text(text)
        return article

    # ------------------------------------------------------------------ CryptoPanic
    async def cryptopanic(self, coin: CoinRef, limit: int = 50) -> list[NewsArticle]:
        if not self.settings.cryptopanic_api_key:
            return []
        try:
            data = await self.http.get_json(
                "cryptopanic",
                CRYPTOPANIC,
                params={
                    "auth_token": self.settings.cryptopanic_api_key,
                    "currencies": coin.symbol.upper(),
                    "public": "true",
                    "kind": "news",
                },
                ttl=self.settings.ttl_news,
            )
        except ProviderError:
            return []
        articles: list[NewsArticle] = []
        for post in (data or {}).get("results") or []:
            try:
                votes = post.get("votes") or {}
                positive = int(votes.get("positive") or 0)
                negative = int(votes.get("negative") or 0)
                raw = None
                if positive or negative:
                    raw = (positive - negative) / max(positive + negative, 1)
                published = post.get("published_at")
                articles.append(
                    NewsArticle(
                        title=post.get("title") or "",
                        url=post.get("url") or post.get("source", {}).get("url", ""),
                        source=(post.get("source") or {}).get("title") or "CryptoPanic",
                        published_at=datetime.fromisoformat(published.replace("Z", "+00:00"))
                        if published
                        else None,
                        summary=(post.get("metadata") or {}).get("description"),
                        currencies=[c.get("code", "") for c in post.get("currencies") or []],
                        sentiment_raw=raw,
                        votes_positive=positive or None,
                        votes_negative=negative or None,
                        panic_score=post.get("panic_score"),
                    )
                )
            except Exception:
                continue
        return articles[:limit]

    # ------------------------------------------------------------------ RSS
    async def rss(self, feeds: list[tuple[str, str]] | None = None) -> list[NewsArticle]:
        feeds = feeds or RSS_FEEDS
        results = await asyncio.gather(
            *[self._parse_feed(name, url) for name, url in feeds], return_exceptions=True
        )
        articles: list[NewsArticle] = []
        for item in results:
            if isinstance(item, list):
                articles.extend(item)
        return articles

    async def _parse_feed(self, name: str, url: str) -> list[NewsArticle]:
        try:
            text = await self.http.get_text("rss", url, ttl=self.settings.ttl_news)
        except ProviderError:
            return []
        parsed = await asyncio.to_thread(feedparser.parse, text)
        articles: list[NewsArticle] = []
        for entry in parsed.entries[:60]:
            published = None
            if getattr(entry, "published_parsed", None):
                published = datetime.fromtimestamp(
                    datetime(*entry.published_parsed[:6], tzinfo=timezone.utc).timestamp(),
                    tz=timezone.utc,
                )
            summary = getattr(entry, "summary", "") or ""
            summary = re.sub(r"<[^>]+>", " ", summary)[:800].strip()
            articles.append(
                NewsArticle(
                    title=getattr(entry, "title", "") or "",
                    url=getattr(entry, "link", "") or "",
                    source=name,
                    published_at=published,
                    summary=summary,
                )
            )
        return articles

    # ------------------------------------------------------------------ Google News
    async def google_news(self, keywords: list[str], limit: int = 40) -> list[NewsArticle]:
        """Google News RSS ile konu bazli arama (anahtarsiz, hizli ve güvenilir)."""
        query = build_topic_query(keywords)
        if not query:
            return []
        try:
            text = await self.http.get_text(
                "google_news",
                GOOGLE_NEWS,
                params={"q": query, "hl": "en", "gl": "US", "ceid": "US:en"},
                ttl=self.settings.ttl_news,
            )
        except ProviderError:
            return []
        parsed = await asyncio.to_thread(feedparser.parse, text)
        articles: list[NewsArticle] = []
        for entry in parsed.entries[:limit]:
            published = None
            if getattr(entry, "published_parsed", None):
                published = datetime.fromtimestamp(
                    datetime(*entry.published_parsed[:6], tzinfo=timezone.utc).timestamp(),
                    tz=timezone.utc,
                )
            source_name = "Google News"
            entry_source = getattr(entry, "source", None)
            if entry_source is not None and getattr(entry_source, "title", None):
                source_name = entry_source.title
            article = NewsArticle(
                title=getattr(entry, "title", "") or "",
                url=getattr(entry, "link", "") or "",
                source=source_name,
                published_at=published,
                summary=re.sub(r"<[^>]+>", " ", getattr(entry, "summary", "") or "")[:600].strip(),
            )
            articles.append(self.score_article(article))
        return articles

    # ------------------------------------------------------------------ GDELT
    async def gdelt(self, coin: CoinRef, hours: int = 24, limit: int = 75) -> list[NewsArticle]:
        query = f'"{coin.name}" OR {coin.symbol.upper()} crypto'
        timespan = f"{hours}h"
        try:
            data = await self.http.get_json(
                "gdelt",
                GDELT_DOC,
                params={
                    "query": query,
                    "mode": "artlist",
                    "maxrecords": limit,
                    "format": "json",
                    "timespan": timespan,
                    "sort": "datedesc",
                },
                ttl=self.settings.ttl_news,
            )
        except ProviderError:
            return []
        articles: list[NewsArticle] = []
        for item in (data or {}).get("articles") or []:
            try:
                seen = item.get("seendate") or ""
                published = datetime.strptime(seen, "%Y%m%dT%H%M%SZ").replace(
                    tzinfo=timezone.utc
                ) if seen else None
                articles.append(
                    NewsArticle(
                        title=item.get("title") or "",
                        url=item.get("url") or "",
                        source=item.get("domain") or "GDELT",
                        published_at=published,
                        language=(item.get("language") or "en").lower()[:2],
                    )
                )
            except Exception:
                continue
        return articles

    async def gdelt_topic(
        self, keywords: list[str], hours: int = 168, limit: int = 40
    ) -> list[NewsArticle]:
        """Bir konu/kriter icin GDELT'te hedefli arama (coin havuzu disinda)."""
        query = build_topic_query(keywords)
        if not query:
            return []
        try:
            data = await self.http.get_json(
                "gdelt",
                GDELT_DOC,
                params={
                    "query": query,
                    "mode": "artlist",
                    "maxrecords": limit,
                    "format": "json",
                    "timespan": f"{hours}h",
                    "sort": "datedesc",
                },
                ttl=self.settings.ttl_news,
            )
        except ProviderError:
            return []
        articles: list[NewsArticle] = []
        for item in (data or {}).get("articles") or []:
            try:
                seen = item.get("seendate") or ""
                published = (
                    datetime.strptime(seen, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
                    if seen
                    else None
                )
                article = NewsArticle(
                    title=item.get("title") or "",
                    url=item.get("url") or "",
                    source=item.get("domain") or "GDELT",
                    published_at=published,
                    language=(item.get("language") or "en").lower()[:2],
                    sentiment_raw=None,
                )
                articles.append(self.score_article(article))
            except Exception:
                continue
        return articles

    async def gdelt_volume(self, coin: CoinRef, hours: int = 24) -> list[dict[str, Any]]:
        """Haber yazilma hızını zaman serisi olarak döndürür (GDELT timeline)."""
        try:
            data = await self.http.get_json(
                "gdelt",
                GDELT_DOC,
                params={
                    "query": f'"{coin.name}" OR {coin.symbol.upper()} crypto',
                    "mode": "timelinevol",
                    "format": "json",
                    "timespan": f"{hours}h",
                },
                ttl=self.settings.ttl_news,
            )
        except ProviderError:
            return []
        timeline = (data or {}).get("timeline") or []
        if not timeline:
            return []
        series = (timeline[0].get("data") or [])
        return [{"date": row.get("date"), "value": row.get("value")} for row in series]

    # ------------------------------------------------------------------ toplama
    def _relevant(self, article: NewsArticle, coin: CoinRef) -> bool:
        haystack = f"{article.title} {article.summary or ''}".lower()
        if coin.symbol.lower() in haystack.split() or f" {coin.symbol.lower()} " in f" {haystack} ":
            return True
        if coin.name.lower() in haystack:
            return True
        return False

    async def fetch_news(self, coin: CoinRef, hours: int = 72, limit: int = 200) -> list[NewsArticle]:
        """Tüm kaynaklardan haberleri toplar, tekilleştirir, sentiment hesaplar ve kaydeder."""
        # Not: GDELT havuz sorgusu yogun 429 verdigi icin kaldirildi; konu bazli
        # aramalar Google News RSS ile yapilir (specials._topic_search), GDELT yalnizca yedek.
        batches = await asyncio.gather(
            self.cryptopanic(coin),
            self.rss(),
            return_exceptions=True,
        )
        collected: list[NewsArticle] = []
        for batch in batches:
            if isinstance(batch, list):
                collected.extend(batch)

        cutoff = utcnow() - timedelta(hours=hours)
        seen: set[str] = set()
        relevant: list[NewsArticle] = []
        general: list[NewsArticle] = []
        for article in collected:
            if not article.title or not article.url:
                continue
            key = hashlib.sha1(article.url.encode("utf-8")).hexdigest()
            if key in seen:
                continue
            seen.add(key)
            if article.published_at and article.published_at < cutoff:
                continue
            article = self.score_article(article)
            if self._relevant(article, coin):
                relevant.append(article)
            else:
                general.append(article)

        relevant.sort(key=lambda a: a.published_at or utcnow(), reverse=True)
        general.sort(key=lambda a: a.published_at or utcnow(), reverse=True)
        final = relevant[:limit]
        if len(final) < 25:
            final.extend(general[: max(10, limit - len(final))])
        self.db.save_articles(coin.id, final)
        return final

    @staticmethod
    def aggregate_sentiment(articles: list[NewsArticle], hours: int = 24) -> dict[str, Any]:
        """Zaman ağırlıklı sentiment özeti."""
        cutoff = utcnow() - timedelta(hours=hours)
        now = utcnow()
        weighted_sum = 0.0
        total_weight = 0.0
        positive = negative = neutral = 0
        for article in articles:
            when = article.published_at or now
            if when < cutoff:
                continue
            age_hours = max((now - when).total_seconds() / 3600, 0.1)
            weight = 1.0 / (1.0 + age_hours / 12.0)
            score = article.sentiment or 0.0
            weighted_sum += score * weight
            total_weight += weight
            if score > 0.15:
                positive += 1
            elif score < -0.15:
                negative += 1
            else:
                neutral += 1
        avg = weighted_sum / total_weight if total_weight else 0.0
        return {
            "avg_sentiment": round(avg, 4),
            "positive": positive,
            "negative": negative,
            "neutral": neutral,
            "sample_size": positive + negative + neutral,
        }
