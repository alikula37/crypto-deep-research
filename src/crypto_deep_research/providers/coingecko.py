"""CoinGecko sağlayıcısi (ücretsiz Demo API)."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from crypto_deep_research.config import Settings
from crypto_deep_research.models import CoinRef, GlobalMarket, MarketSnapshot, utcnow
from crypto_deep_research.providers.base import CachedHTTP, ProviderError, source
from crypto_deep_research.storage.db import Database

logger = logging.getLogger(__name__)

BASE = "https://api.coingecko.com/api/v3"

SYMBOL_ALIASES: dict[str, str] = {
    "btc": "bitcoin",
    "eth": "ethereum",
    "sol": "solana",
    "bnb": "binancecoin",
    "xrp": "ripple",
    "ada": "cardano",
    "doge": "dogecoin",
    "avax": "avalanche-2",
    "dot": "polkadot",
    "link": "chainlink",
    "matic": "matic-network",
    "pol": "polygon-ecosystem-token",
    "ltc": "litecoin",
    "trx": "tron",
    "ton": "the-open-network",
    "shib": "shiba-inu",
    "atom": "cosmos",
    "near": "near",
    "apt": "aptos",
    "arb": "arbitrum",
    "op": "optimism",
    "sui": "sui",
    "icp": "internet-computer",
    "etc": "ethereum-classic",
    "xlm": "stellar",
    "fil": "filecoin",
    "inj": "injective-protocol",
    "sei": "sei-network",
    "tia": "celestia",
    "rune": "thorchain",
    "aave": "aave",
    "uni": "uniswap",
    "pepe": "pepe",
    "bonk": "bonk",
}


def _dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


class CoinGeckoProvider:
    name = "coingecko"
    base = BASE

    def __init__(self, http: CachedHTTP, db: Database, settings: Settings) -> None:
        self.http = http
        self.db = db
        self.settings = settings
        self._coin_list: list[dict[str, Any]] | None = None

    @property
    def _headers(self) -> dict[str, str]:
        if self.settings.coingecko_api_key:
            return {"x-cg-demo-api-key": self.settings.coingecko_api_key}
        return {}

    async def _get(self, path: str, params: dict[str, Any] | None = None, ttl: int = 300) -> Any:
        url = f"{self.base}{path}"
        return await self.http.get_json(self.name, url, params=params, headers=self._headers, ttl=ttl)

    # ------------------------------------------------------------- coin cozumleme
    async def coin_list(self) -> list[dict[str, Any]]:
        if self._coin_list is None:
            data = await self._get("/coins/list", ttl=self.settings.ttl_static)
            self._coin_list = data if isinstance(data, list) else []
        return self._coin_list

    def coin_list_cached(self) -> list[dict[str, Any]]:
        cache_key = "coingecko-coins-list"
        cached = self.db.cache_get(cache_key)
        if cached:
            return cached[0]
        return self._coin_list or []

    async def resolve(self, query: str) -> CoinRef:
        """Sembol veya isimden CoinRef cozer."""
        token = query.strip().lower()
        if token in SYMBOL_ALIASES:
            coin_id = SYMBOL_ALIASES[token]
            return CoinRef(id=coin_id, symbol=token, name=token.upper())

        coin_list = await self.coin_list()
        exact_id = next((c for c in coin_list if c["id"] == token), None)
        if exact_id:
            return CoinRef(id=exact_id["id"], symbol=exact_id["symbol"], name=exact_id["name"])

        symbol_matches = [c for c in coin_list if c["symbol"].lower() == token]
        if symbol_matches:
            if len(symbol_matches) > 1:
                markets = await self.markets([c["id"] for c in symbol_matches[:25]])
                ranked = sorted(
                    markets,
                    key=lambda m: m.get("market_cap_rank") or 10**9,
                )
                if ranked:
                    top = ranked[0]
                    return CoinRef(
                        id=top["id"],
                        symbol=top.get("symbol", token),
                        name=top.get("name", token.upper()),
                    )
            chosen = symbol_matches[0]
            return CoinRef(id=chosen["id"], symbol=chosen["symbol"], name=chosen["name"])

        name_matches = [c for c in coin_list if c["name"].lower() == token]
        if name_matches:
            chosen = name_matches[0]
            return CoinRef(id=chosen["id"], symbol=chosen["symbol"], name=chosen["name"])
        raise ProviderError(self.name, f"Coin bulunamadı: {query}")

    # ------------------------------------------------------------- market verisi
    async def markets(self, ids: list[str] | None = None, per_page: int = 100, page: int = 1) -> list[dict]:
        params: dict[str, Any] = {
            "vs_currency": "usd",
            "order": "market_cap_desc",
            "per_page": per_page,
            "page": page,
            "sparkline": "false",
            "price_change_percentage": "1h,24h,7d,30d",
        }
        if ids:
            params["ids"] = ",".join(ids)
            params["per_page"] = max(len(ids), 1)
        data = await self._get("/coins/markets", params, ttl=self.settings.ttl_market)
        return data if isinstance(data, list) else []

    async def snapshot(self, coin: CoinRef) -> MarketSnapshot:
        data = await self.markets([coin.id])
        if not data:
            raise ProviderError(self.name, f"Market verisi yok: {coin.id}")
        return self.snapshot_from_market(data[0], coin)

    @staticmethod
    def snapshot_from_market(item: dict[str, Any], coin: CoinRef) -> MarketSnapshot:
        return MarketSnapshot(
            coin=coin,
            price_usd=float(item.get("current_price") or 0.0),
            market_cap_usd=item.get("market_cap"),
            fully_diluted_valuation_usd=item.get("fully_diluted_valuation"),
            rank=item.get("market_cap_rank"),
            volume_24h_usd=item.get("total_volume"),
            change_1h_pct=item.get("price_change_percentage_1h_in_currency"),
            change_24h_pct=item.get("price_change_percentage_24h_in_currency"),
            change_7d_pct=item.get("price_change_percentage_7d_in_currency"),
            change_30d_pct=item.get("price_change_percentage_30d_in_currency"),
            ath_usd=item.get("ath"),
            ath_date=_dt(item.get("ath_date")),
            ath_change_pct=item.get("ath_change_percentage"),
            atl_usd=item.get("atl"),
            atl_date=_dt(item.get("atl_date")),
            atl_change_pct=item.get("atl_change_percentage"),
            circulating_supply=item.get("circulating_supply"),
            total_supply=item.get("total_supply"),
            max_supply=item.get("max_supply"),
            fetched_at=utcnow(),
        )

    async def coin_detail(self, coin_id: str) -> dict[str, Any]:
        return await self._get(
            f"/coins/{coin_id}",
            {
                "localization": "false",
                "tickers": "false",
                "market_data": "true",
                "community_data": "false",
                "developer_data": "false",
                "sparkline": "false",
            },
            ttl=self.settings.ttl_static,
        )

    async def categories(self, coin_id: str) -> list[str]:
        try:
            detail = await self.coin_detail(coin_id)
            return list(detail.get("categories") or [])
        except ProviderError:
            return []

    async def market_chart(self, coin_id: str, days: int = 365) -> dict[str, Any]:
        ttl = self.settings.ttl_market if days <= 1 else self.settings.ttl_ohlcv * 2
        return await self._get(
            f"/coins/{coin_id}/market_chart",
            {"vs_currency": "usd", "days": days},
            ttl=max(ttl, 300),
        )

    async def ohlc(self, coin_id: str, days: int = 90) -> list[list[float]]:
        data = await self._get(
            f"/coins/{coin_id}/ohlc",
            {"vs_currency": "usd", "days": days},
            ttl=self.settings.ttl_ohlcv,
        )
        return data if isinstance(data, list) else []

    async def tickers(self, coin_id: str) -> list[dict[str, Any]]:
        data = await self._get(
            f"/coins/{coin_id}/tickers",
            {"include_exchange_logo": "false", "depth": "false", "order": "volume_desc"},
            ttl=self.settings.ttl_market,
        )
        return list((data or {}).get("tickers") or [])

    async def global_market(self) -> GlobalMarket:
        data = await self._get("/global", ttl=self.settings.ttl_market)
        d = (data or {}).get("data") or {}
        return GlobalMarket(
            total_market_cap_usd=(d.get("total_market_cap") or {}).get("usd"),
            total_volume_usd=(d.get("total_volume") or {}).get("usd"),
            btc_dominance=(d.get("market_cap_percentage") or {}).get("btc"),
            eth_dominance=(d.get("market_cap_percentage") or {}).get("eth"),
            market_cap_change_24h_pct=d.get("market_cap_change_percentage_24h_usd"),
            active_cryptocurrencies=d.get("active_cryptocurrencies"),
            fetched_at=utcnow(),
        )

    async def trending(self) -> list[dict[str, Any]]:
        data = await self._get("/search/trending", ttl=600)
        return list((data or {}).get("coins") or [])

    async def coins_categories(self) -> list[dict[str, Any]]:
        data = await self._get(
            "/coins/categories", {"order": "market_cap_desc"}, ttl=1800
        )
        return data if isinstance(data, list) else []

    def sources(self, path: str | None = None) -> list:
        url = f"{self.base}{path}" if path else self.base
        return [source("CoinGecko", url)]
