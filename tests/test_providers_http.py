"""Ag saglayicilari: respx ile sahte HTTP, onbellek ve stale fallback davranisi."""

from __future__ import annotations

import httpx
import pytest
import respx

from crypto_deep_research.models import CoinRef
from crypto_deep_research.providers.base import ProviderError
from crypto_deep_research.providers.coingecko import CoinGeckoProvider
from crypto_deep_research.providers.defillama import DefiLlamaProvider
from crypto_deep_research.providers.exchange import ExchangeProvider
from crypto_deep_research.providers.news import NewsProvider

COINGECKO_MARKETS_URL = "https://api.coingecko.com/api/v3/coins/markets"

MARKET_ITEM = {
    "id": "pepe",
    "symbol": "pepe",
    "name": "Pepe",
    "current_price": 0.00000338,
    "market_cap": 1_421_000_000,
    "fully_diluted_valuation": 1_421_000_000,
    "market_cap_rank": 60,
    "total_volume": 267_000_000,
    "price_change_percentage_1h_in_currency": 0.1,
    "price_change_percentage_24h_in_currency": 1.9,
    "price_change_percentage_7d_in_currency": -4.7,
    "price_change_percentage_30d_in_currency": 22.9,
    "ath": 0.00002803,
    "ath_date": "2024-12-10T00:00:00.000Z",
    "ath_change_percentage": -87.9,
    "atl": 0.00000005514,
    "atl_date": "2023-04-18T00:00:00.000Z",
    "atl_change_percentage": 6029.6,
    "circulating_supply": 420_690_000_000_000.0,
    "total_supply": 420_690_000_000_000.0,
    "max_supply": 420_690_000_000_000.0,
}


@respx.mock
async def test_coingecko_snapshot_parsing_and_cache(http, db, settings):
    route = respx.get(COINGECKO_MARKETS_URL).mock(
        return_value=httpx.Response(200, json=[MARKET_ITEM])
    )
    provider = CoinGeckoProvider(http, db, settings)
    coin = CoinRef(id="pepe", symbol="pepe", name="Pepe")

    snapshot = await provider.snapshot(coin)
    assert snapshot.price_usd == 0.00000338
    assert snapshot.rank == 60
    assert snapshot.ath_change_pct == -87.9
    assert snapshot.distance_from_ath_pct < 0

    await provider.snapshot(coin)
    assert route.call_count == 1, "ikinci cagri onbellekten gelmeli"


@respx.mock
async def test_coingecko_snapshot_empty_raises(http, db, settings):
    respx.get(COINGECKO_MARKETS_URL).mock(return_value=httpx.Response(200, json=[]))
    provider = CoinGeckoProvider(http, db, settings)
    with pytest.raises(ProviderError):
        await provider.snapshot(CoinRef(id="yok", symbol="yok", name="Yok"))


@respx.mock
async def test_coingecko_resolve_by_symbol(http, db, settings):
    respx.get("https://api.coingecko.com/api/v3/coins/list").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"id": "pepe", "symbol": "pepe", "name": "Pepe"},
                {"id": "pepe-2", "symbol": "pepe", "name": "Pepe 2"},
            ],
        )
    )
    respx.get(COINGECKO_MARKETS_URL).mock(
        return_value=httpx.Response(
            200,
            json=[
                {**MARKET_ITEM, "id": "pepe", "market_cap_rank": 60},
                {**MARKET_ITEM, "id": "pepe-2", "market_cap_rank": 900},
            ],
        )
    )
    provider = CoinGeckoProvider(http, db, settings)
    resolved = await provider.resolve("pepe")
    assert resolved.id == "pepe"


@respx.mock
async def test_http_cache_stale_fallback(http, db, settings):
    url = "https://example.test/data"
    route = respx.get(url).mock(return_value=httpx.Response(200, json={"value": 1}))
    assert await http.get_json("unit", url, ttl=0) == {"value": 1}

    route.mock(return_value=httpx.Response(500, text="boom"))
    assert await http.get_json("unit", url, ttl=0) == {"value": 1}
    assert route.call_count == 2, "hata durumunda stale onbellek kullanilmali"


@respx.mock
async def test_binance_klines_parse_and_symbol(http, settings):
    route = respx.get("https://api.binance.com/api/v3/klines").mock(
        return_value=httpx.Response(
            200,
            json=[
                [
                    1735689600000,
                    "0.00000300",
                    "0.00000320",
                    "0.00000290",
                    "0.00000310",
                    "1500000",
                ]
            ],
        )
    )
    provider = ExchangeProvider(http, settings)
    klines = await provider.klines("pepe", "1d", limit=10)
    assert len(klines) == 1
    assert klines[0].open == 3e-06
    assert route.calls[0].request.url.params["symbol"] == "PEPEUSDT"


@respx.mock
async def test_multi_exchange_tickers(http, settings):
    respx.get("https://api.binance.com/api/v3/ticker/24hr").mock(
        return_value=httpx.Response(
            200,
            json={
                "lastPrice": "10.5",
                "quoteVolume": "1000000",
                "priceChangePercent": "2.5",
                "count": 42,
            },
        )
    )
    respx.get("https://www.okx.com/api/v5/market/ticker").mock(
        return_value=httpx.Response(200, json={"data": [{"last": "10.6", "volCcy24h": "900000"}]})
    )
    respx.get("https://api.bybit.com/v5/market/tickers").mock(
        return_value=httpx.Response(
            200,
            json={
                "result": {
                    "list": [
                        {"lastPrice": "10.4", "turnover24h": "800000", "price24hPcnt": "0.01"}
                    ]
                }
            },
        )
    )
    provider = ExchangeProvider(http, settings)
    tickers = await provider.multi_exchange_tickers("sol")
    assert set(tickers) == {"Binance", "OKX", "Bybit"}
    assert tickers["Binance"]["price_usd"] == 10.5
    assert round(tickers["Bybit"]["change_24h_pct"], 2) == 1.0


def test_news_sentiment_lexicon(settings, db, http):
    provider = NewsProvider(http, db, settings)
    assert provider.score_text("Bitcoin ETF approval sparks rally") > 0
    assert provider.score_text("Exchange hack causes crash") < 0


def test_defillama_summarize_fees():
    data = {
        "total24h": 1_000_000,
        "total7d": 7_000_000,
        "total30d": 30_000_000,
        "total1y": 365_000_000,
        "change_1d": 1.2,
        "change_7d": 12.5,
        "change_30d": -3.0,
        "name": "Ethereum",
        "dataType": "dailyRevenue",
    }
    summary = DefiLlamaProvider.summarize_fees(data)
    assert summary["total_24h_usd"] == 1_000_000
    assert summary["change_7d_pct"] == 12.5
    assert summary["revenue_24h_usd"] == 1_000_000


def test_defillama_summarize_fees_empty():
    assert DefiLlamaProvider.summarize_fees(None) == {}


COINGECKO_SEARCH_URL = "https://api.coingecko.com/api/v3/search"
COINGECKO_LIST_URL = "https://api.coingecko.com/api/v3/coins/list"


@respx.mock
async def test_coingecko_search_parsing(http, db, settings):
    respx.get(COINGECKO_SEARCH_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "coins": [
                    {"id": "chainlink", "name": "Chainlink", "symbol": "link", "market_cap_rank": 12},
                    {"id": "link", "name": "Link", "symbol": "lnk", "market_cap_rank": 950},
                ]
            },
        )
    )
    provider = CoinGeckoProvider(http, db, settings)
    results = await provider.search("link", limit=5)
    assert [item["id"] for item in results] == ["chainlink", "link"]
    assert results[0]["symbol"] == "LINK"
    assert results[0]["rank"] == 12


@respx.mock
async def test_coingecko_search_fallback_on_error(http, db, settings):
    respx.get(COINGECKO_SEARCH_URL).mock(return_value=httpx.Response(500, text="boom"))
    respx.get(COINGECKO_LIST_URL).mock(
        return_value=httpx.Response(
            200,
            json=[
                {"id": "chainlink", "symbol": "link", "name": "Chainlink"},
                {"id": "link", "symbol": "lnk", "name": "Link"},
                {"id": "bitcoin", "symbol": "btc", "name": "Bitcoin"},
            ],
        )
    )
    provider = CoinGeckoProvider(http, db, settings)
    results = await provider.search("chain", limit=5)
    assert results and results[0]["id"] == "chainlink"


async def test_coingecko_search_empty_query(http, db, settings):
    provider = CoinGeckoProvider(http, db, settings)
    assert await provider.search("   ") == []
