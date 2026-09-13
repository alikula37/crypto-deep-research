"""Hedefli haber arama testleri: Google News -> GDELT yedegi (ag erisimi olmadan)."""

from types import SimpleNamespace

from crypto_deep_research.deep_research.registry import ItemSpec
from crypto_deep_research.deep_research.specials import _news_item
from crypto_deep_research.models import NewsArticle
from crypto_deep_research.providers.news import build_topic_query


def test_build_topic_query():
    query = build_topic_query(["war", "sanction", "conflict", "tariff", "fifth"])
    assert query == '("war" OR "sanction" OR "conflict" OR "tariff")'
    assert build_topic_query([]) == ""
    assert build_topic_query(["a", "bb"]) == ""
    assert build_topic_query(['quo"te', "war"]) == '("quote" OR "war")'


def _spec() -> ItemSpec:
    return ItemSpec(
        id=10,
        title_tr="Global Jeopolitik Olaylar",
        description_tr="test",
        category="Haber",
        source="news",
        query="geopolitics war sanctions",
        keywords=["war", "sanction", "conflict"],
        weight=0.3,
    )


def _article(title: str, sentiment: float, url: str) -> NewsArticle:
    return NewsArticle(title=title, url=url, source="test", sentiment=sentiment)


class _StubNews:
    def __init__(self, google=None, gdelt=None):
        self.google = google or []
        self.gdelt = gdelt or []
        self.google_calls = 0
        self.gdelt_calls = 0

    async def google_news(self, keywords, limit=40):
        self.google_calls += 1
        return list(self.google)

    async def gdelt_topic(self, keywords, hours=168, limit=40):
        self.gdelt_calls += 1
        return list(self.gdelt)


class _StubCtx:
    def __init__(self, pool, news):
        self._pool = pool
        self.providers = SimpleNamespace(news=news)
        self.extra = {}

    async def articles(self, hours=72):
        return list(self._pool)


POOL = [_article("Bitcoin ETF inflows rise", 0.5, "u1")]
TOPIC = [
    _article("New sanctions hit global markets", -0.8, "u2"),
    _article("War risk pushes investors to safety", -0.6, "u3"),
    _article("Conflict escalates in region", -0.7, "u4"),
]


async def test_google_news_preferred():
    news = _StubNews(google=TOPIC)
    ctx = _StubCtx(POOL, news)
    result = await _news_item(ctx, _spec())
    assert result.status == "ok"
    assert result.score is not None and result.score < 0
    assert result.data.get("search") == "google_news"
    assert result.data.get("matched") == 3
    assert news.google_calls == 1
    assert news.gdelt_calls == 0
    assert "Google News" in result.summary


async def test_gdelt_fallback_when_google_empty():
    news = _StubNews(google=[], gdelt=TOPIC)
    ctx = _StubCtx(POOL, news)
    result = await _news_item(ctx, _spec())
    assert result.status == "ok"
    assert result.data.get("search") == "gdelt_topic"
    assert news.google_calls == 1
    assert news.gdelt_calls == 1


async def test_no_data_when_both_backends_empty():
    news = _StubNews()
    ctx = _StubCtx(POOL, news)
    result = await _news_item(ctx, _spec())
    assert result.status == "no_data"
    assert result.score is None
    assert news.google_calls == 1
    assert news.gdelt_calls == 1
