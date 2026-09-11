"""Saglayici kayit defteri: tum saglayicilari tek nesnede toplar."""

from __future__ import annotations

from dataclasses import dataclass

from crypto_deep_research.config import Settings
from crypto_deep_research.providers.base import CachedHTTP
from crypto_deep_research.providers.coinalyze import CoinalyzeProvider
from crypto_deep_research.providers.coingecko import CoinGeckoProvider
from crypto_deep_research.providers.defillama import DefiLlamaProvider
from crypto_deep_research.providers.exchange import ExchangeProvider
from crypto_deep_research.providers.macro import MacroProvider
from crypto_deep_research.providers.news import NewsProvider
from crypto_deep_research.providers.onchain import OnChainProvider
from crypto_deep_research.providers.sentiment import SentimentProvider
from crypto_deep_research.storage.db import Database


@dataclass
class Providers:
    http: CachedHTTP
    db: Database
    settings: Settings
    coingecko: CoinGeckoProvider
    exchange: ExchangeProvider
    coinalyze: CoinalyzeProvider
    defillama: DefiLlamaProvider
    news: NewsProvider
    sentiment: SentimentProvider
    onchain: OnChainProvider
    macro: MacroProvider

    async def aclose(self) -> None:
        await self.http.aclose()


def build_providers(settings: Settings, db: Database | None = None) -> Providers:
    db = db or Database(settings.db_path)
    http = CachedHTTP(db, settings)
    return Providers(
        http=http,
        db=db,
        settings=settings,
        coingecko=CoinGeckoProvider(http, db, settings),
        exchange=ExchangeProvider(http, settings),
        coinalyze=CoinalyzeProvider(http, settings),
        defillama=DefiLlamaProvider(http, settings),
        news=NewsProvider(http, db, settings),
        sentiment=SentimentProvider(http, settings),
        onchain=OnChainProvider(http, settings),
        macro=MacroProvider(http, db, settings),
    )
