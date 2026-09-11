"""Analiz baglami ve yardimci fonksiyonlar."""

from __future__ import annotations

from dataclasses import dataclass, field

from crypto_deep_research.config import Settings
from crypto_deep_research.models import (
    AnalysisResult,
    CoinRef,
    GlobalMarket,
    Kline,
    MarketSnapshot,
    NewsArticle,
    SourceRef,
)
from crypto_deep_research.providers.registry import Providers


@dataclass
class AnalysisContext:
    """Tum analizlere verilen ortak baglam."""

    coin: CoinRef
    providers: Providers
    settings: Settings
    timeframe: str = "1d"
    lookback_days: int = 365
    platform: str = "generic"
    _snapshot: MarketSnapshot | None = None
    _global: GlobalMarket | None = None
    _klines: list[Kline] | None = None
    _articles: list[NewsArticle] | None = None
    _detail: dict | None = None
    extra: dict = field(default_factory=dict)

    @property
    def db(self):
        return self.providers.db

    async def snapshot(self) -> MarketSnapshot:
        if self._snapshot is None:
            self._snapshot = await self.providers.coingecko.snapshot(self.coin)
            self.db.save_snapshot(self.coin.id, self._snapshot.model_dump(mode="json"))
        return self._snapshot

    async def global_market(self) -> GlobalMarket:
        if self._global is None:
            self._global = await self.providers.coingecko.global_market()
        return self._global

    async def klines(self, limit: int = 500) -> list[Kline]:
        if self._klines is None:
            self._klines = await self.providers.exchange.klines(
                self.coin.symbol, self.timeframe, limit
            )
            if not self._klines:
                days = min(self.lookback_days, 365)
                raw = await self.providers.coingecko.ohlc(self.coin.id, days=max(days, 30))
                self._klines = [
                    Kline(
                        ts=__import__("datetime").datetime.fromtimestamp(
                            row[0] / 1000, tz=__import__("datetime").timezone.utc
                        ),
                        open=float(row[1]),
                        high=float(row[2]),
                        low=float(row[3]),
                        close=float(row[4]),
                        volume=0.0,
                    )
                    for row in raw
                ]
        return self._klines

    async def articles(self, hours: int = 72) -> list[NewsArticle]:
        if self._articles is None:
            self._articles = await self.providers.news.fetch_news(
                self.coin, hours=hours, limit=200
            )
        return self._articles

    async def coin_detail(self) -> dict:
        if self._detail is None:
            try:
                self._detail = await self.providers.coingecko.coin_detail(self.coin.id)
            except Exception:
                self._detail = {}
        return self._detail

    def result(
        self,
        key: str,
        title: str,
        *,
        status: str = "ok",
        summary: str = "",
        data: dict | None = None,
        sources: list[SourceRef] | None = None,
        score: float | None = None,
        confidence: float = 0.0,
        warnings: list[str] | None = None,
    ) -> AnalysisResult:
        return AnalysisResult(
            key=key,
            title=title,
            status=status,  # type: ignore[arg-type]
            summary=summary,
            data=data or {},
            sources=sources or [],
            score=score,
            confidence=confidence,
            warnings=warnings or [],
        )


def clamp(value: float, low: float = -1.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def pct_change(current: float | None, previous: float | None) -> float | None:
    if current is None or previous in (None, 0):
        return None
    return (current / previous - 1.0) * 100.0


def rank_to_score(rank: int | None, baseline: int = 100) -> float:
    """Kucuk rank (yuksek mcap) pozitif; rank kotulesince negatif."""
    if rank is None:
        return 0.0
    return clamp((baseline - rank) / baseline)


def trend_score(change_pct: float | None, scale: float = 10.0) -> float:
    if change_pct is None:
        return 0.0
    return clamp(change_pct / scale)
