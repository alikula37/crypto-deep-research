"""DefiLlama sağlayıcısi: protokol gelirleri, fee, stablecoin ve bridge verileri (ücretsiz)."""

from __future__ import annotations

import logging
from typing import Any

from crypto_deep_research.config import Settings
from crypto_deep_research.providers.base import CachedHTTP, ProviderError

logger = logging.getLogger(__name__)

BASE = "https://api.llama.fi"
STABLECOINS = "https://stablecoins.llama.fi"
BRIDGES = "https://bridges.llama.fi"

# CoinGecko id -> DefiLlama slug eslemeleri
SLUG_ALIASES: dict[str, str] = {
    "bitcoin": "bitcoin",
    "ethereum": "ethereum",
    "solana": "solana",
    "binancecoin": "bsc",
    "tron": "tron",
    "avalanche-2": "avalanche",
    "polygon-ecosystem-token": "polygon",
    "matic-network": "polygon",
    "arbitrum": "arbitrum",
    "optimism": "optimism",
    "base": "base",
    "sui": "sui",
    "aptos": "aptos",
    "near": "near",
    "cosmos": "cosmos",
    "litecoin": "litecoin",
    "dogecoin": "dogecoin",
    "ripple": "ripple",
    "cardano": "cardano",
    "the-open-network": "ton",
    "uniswap": "uniswap",
    "aave": "aave",
    "chainlink": "chainlink",
    "lido": "lido",
    "maker": "makerdao",
    "curve-dao-token": "curve-dex",
    "jupiter": "jupiter",
    "hyperliquid": "hyperliquid",
}


class DefiLlamaProvider:
    name = "defillama"

    def __init__(self, http: CachedHTTP, settings: Settings) -> None:
        self.http = http
        self.settings = settings

    @staticmethod
    def slug_for(coin_id: str) -> str:
        return SLUG_ALIASES.get(coin_id, coin_id)

    async def fees_summary(self, coin_id: str, data_type: str = "dailyFees") -> dict[str, Any] | None:
        """Protokol/zincir ücret ve gelir özeti."""
        slug = self.slug_for(coin_id)
        for path in (f"/summary/fees/{slug}", f"/overview/fees/{slug}"):
            try:
                data = await self.http.get_json(
                    self.name, f"{BASE}{path}", params={"dataType": data_type}, ttl=3600
                )
                if data:
                    return data
            except ProviderError:
                continue
        return None

    async def protocol(self, coin_id: str) -> dict[str, Any] | None:
        slug = self.slug_for(coin_id)
        try:
            return await self.http.get_json(self.name, f"{BASE}/protocol/{slug}", ttl=3600)
        except ProviderError:
            return None

    async def stablecoins(self) -> dict[str, Any] | None:
        try:
            return await self.http.get_json(
                self.name,
                f"{STABLECOINS}/stablecoins",
                params={"includePrices": "false"},
                ttl=1800,
            )
        except ProviderError:
            return None

    async def stablecoin_charts_all(self) -> list[dict[str, Any]]:
        try:
            data = await self.http.get_json(
                self.name, f"{STABLECOINS}/stablecoincharts/all", ttl=3600
            )
            return data if isinstance(data, list) else []
        except ProviderError:
            return []

    async def bridges(self) -> list[dict[str, Any]]:
        try:
            data = await self.http.get_json(
                self.name, f"{BRIDGES}/bridges", params={"includeChains": "true"}, ttl=3600
            )
            return list((data or {}).get("bridges") or [])
        except ProviderError:
            return []

    async def chains(self) -> list[dict[str, Any]]:
        try:
            data = await self.http.get_json(self.name, f"{BASE}/v2/chains", ttl=3600)
            return data if isinstance(data, list) else []
        except ProviderError:
            return []

    @staticmethod
    def summarize_fees(data: dict[str, Any] | None) -> dict[str, Any]:
        """DefiLlama fee/gelir verisini özetler."""
        if not data:
            return {}
        total_24h = data.get("total24h")
        total_7d = data.get("total7d")
        total_30d = data.get("total30d")
        revenue_24h = data.get("total24h") if data.get("dataType") == "dailyRevenue" else None
        out = {
            "name": data.get("name") or data.get("displayName"),
            "total_24h_usd": total_24h,
            "total_7d_usd": total_7d,
            "total_30d_usd": total_30d,
            "total_1y_usd": data.get("total1y"),
            "average_24h_usd": total_24h,
            "change_1d_pct": data.get("change_1d"),
            "change_7d_pct": data.get("change_7d"),
            "change_30d_pct": data.get("change_30d"),
        }
        if revenue_24h is not None:
            out["revenue_24h_usd"] = revenue_24h
        return {k: v for k, v in out.items() if v is not None}
