"""Zincir-Üstü (on-chain) sağlayıcılar: Blockchain.com, mempool.space, Blockchair, Blockscout/Etherscan, balina taraması."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from crypto_deep_research.config import Settings
from crypto_deep_research.models import WhaleFlow, utcnow
from crypto_deep_research.providers.base import CachedHTTP, ProviderError

logger = logging.getLogger(__name__)

BLOCKCHAIN_COM = "https://api.blockchain.info"
MEMPOOL = "https://mempool.space/api"
BLOCKCHAIR = "https://api.blockchair.com"
BLOCKSCOUT_ETH = "https://eth.blockscout.com/api/v2"
ETHERSCAN = "https://api.etherscan.io/api"

BLOCKCHAIN_CHARTS: dict[str, str] = {
    "hash_rate": "hash-rate",
    "unique_addresses": "n-unique-addresses",
    "transaction_fees_usd": "transaction-fees-usd",
    "mempool_size": "mempool-size",
    "miners_revenue_usd": "miners-revenue",
    "tx_volume_usd": "estimated-transaction-volume-usd",
    "n_transactions": "n-transactions",
    "total_bitcoins": "total-bitcoins",
}

# Kamuya açık, bilinen büyük borsa cüzdanları (adres etiketleri kamu kaynaklarından;
# etiketler doğrulama gerektirebilir, yanlis atif riskine karsi "known label" olarak işaretlenir).
KNOWN_EXCHANGE_ADDRESSES: dict[str, dict[str, str]] = {
    "ethereum": {
        "0x28c6c06298d514db089934071355e5743bf21d60": "Binance 14",
        "0x21a31ee1afc51d94c2efccaa2092ad1028285549": "Binance 15",
        "0xdfd5293d8e347dfe59e90efd55b2956a1343963d": "Binance 16",
        "0x56eddb7aa87536c09ccc2793473599fd21a8b17f": "Binance 17",
        "0x71660c4005bae913eae4147586f7fac99ccbfb3b": "Coinbase 1",
        "0x503828976d22510aad0201ac7ec88293211d23da": "Coinbase 2",
        "0xddfabcdc4d8ffc6d5beaf154f18b778f68cbea6c": "Coinbase 3",
        "0x2910543af39aba0cd09dbb2d50200b3e800a63d2": "Kraken 1",
        "0x6cc5f688a315f3dc28a7781717a9a798a59fda7b": "OKX 1",
        "0x236f9f97e0e62388479bf9e5ba4889e46b0273c3": "OKX 2",
    },
    "bitcoin": {
        "34xp4vRoCGJym3xR7yCVPFHoCNxv4Twseo": "Binance cold wallet",
        "3FHNBLobJnbCTFTVakh5TXmEneyf5PT61B": "Coinbase cold wallet",
    },
}


class OnChainProvider:
    name = "onchain"

    def __init__(self, http: CachedHTTP, settings: Settings) -> None:
        self.http = http
        self.settings = settings

    # ------------------------------------------------------------------ Blockchain.com
    async def blockchain_chart(self, chart: str, timespan: str = "30days") -> list[dict[str, Any]]:
        key = BLOCKCHAIN_CHARTS.get(chart, chart)
        try:
            data = await self.http.get_json(
                "blockchain_com",
                f"{BLOCKCHAIN_COM}/charts/{key}",
                params={"format": "json", "timespan": timespan},
                ttl=self.settings.ttl_onchain,
            )
        except ProviderError:
            return []
        return list((data or {}).get("values") or [])

    async def btc_network_stats(self) -> dict[str, Any]:
        charts = ["hash_rate", "unique_addresses", "transaction_fees_usd", "miners_revenue_usd", "mempool_size", "n_transactions"]
        results = await asyncio.gather(
            *[self.blockchain_chart(chart) for chart in charts], return_exceptions=True
        )
        out: dict[str, Any] = {}
        for chart, values in zip(charts, results, strict=False):
            if not isinstance(values, list) or not values:
                continue
            latest = values[-1].get("y")
            first = values[0].get("y")
            change_pct = ((latest - first) / first * 100) if first else None
            out[chart] = {
                "latest": latest,
                "change_pct": round(change_pct, 2) if change_pct is not None else None,
                "points": len(values),
            }
        return out

    # ------------------------------------------------------------------ mempool.space
    async def mempool_fees(self) -> dict[str, Any] | None:
        try:
            return await self.http.get_json(
                "mempool", f"{MEMPOOL}/v1/fees/recommended", ttl=300
            )
        except ProviderError:
            return None

    async def mempool_hashrate(self) -> dict[str, Any] | None:
        try:
            return await self.http.get_json(
                "mempool", f"{MEMPOOL}/v1/mining/hashrate/3d", ttl=self.settings.ttl_onchain
            )
        except ProviderError:
            return None

    # ------------------------------------------------------------------ Blockchair
    async def blockchair_stats(self, chain: str = "bitcoin") -> dict[str, Any] | None:
        try:
            data = await self.http.get_json(
                "blockchair",
                f"{BLOCKCHAIR}/{chain}/stats",
                ttl=self.settings.ttl_onchain,
            )
            return (data or {}).get("data")
        except ProviderError:
            return None

    # ------------------------------------------------------------------ Etherscan
    async def etherscan_gas(self) -> dict[str, Any] | None:
        params: dict[str, Any] = {"module": "gastracker", "action": "gasoracle"}
        if self.settings.etherscan_api_key:
            params["apikey"] = self.settings.etherscan_api_key
        try:
            data = await self.http.get_json("etherscan", ETHERSCAN, params=params, ttl=300)
            return (data or {}).get("result")
        except ProviderError:
            return None

    # ------------------------------------------------------------------ Balina taraması
    async def btc_large_transactions(self, min_btc: float = 50.0, limit: int = 100) -> list[WhaleFlow]:
        """Son bloklardaki büyük BTC transferlerini tarar (mempool.space, yedek: blockchain.info)."""
        flows = await self._mempool_space_large(min_btc)
        if flows:
            return flows[:limit]
        return await self._blockchain_info_large(min_btc, limit)

    async def _mempool_space_large(self, min_btc: float) -> list[WhaleFlow]:
        try:
            blocks = await self.http.get_json("mempool", f"{MEMPOOL}/v1/blocks", ttl=60)
        except ProviderError:
            return []
        known = KNOWN_EXCHANGE_ADDRESSES["bitcoin"]
        flows: list[WhaleFlow] = []
        for block in (blocks or [])[:3]:
            block_id = block.get("id")
            if not block_id:
                continue
            try:
                txs = await self.http.get_json(
                    "mempool", f"{MEMPOOL}/block/{block_id}/txs", ttl=300
                )
            except ProviderError:
                continue
            timestamp = datetime.fromtimestamp(
                int(block.get("timestamp") or utcnow().timestamp()), tz=timezone.utc
            )
            for tx in txs or []:
                try:
                    value_sat = sum(int(vout.get("value") or 0) for vout in tx.get("vout") or [])
                    btc = value_sat / 1e8
                    if btc < min_btc:
                        continue
                    addresses = [
                        str(vout.get("scriptpubkey_address") or "")
                        for vout in tx.get("vout") or []
                    ]
                    counterparty = next(
                        (known[address] for address in addresses if address in known), None
                    )
                    flows.append(
                        WhaleFlow(
                            chain="bitcoin",
                            tx_hash=tx.get("txid"),
                            amount=btc,
                            amount_usd=0.0,
                            direction="exchange_in" if counterparty else "unknown",  # type: ignore[arg-type]
                            counterparty=counterparty,
                            timestamp=timestamp,
                            source="mempool.space",
                        )
                    )
                except Exception:
                    continue
        return flows

    async def _blockchain_info_large(self, min_btc: float, limit: int) -> list[WhaleFlow]:
        try:
            data = await self.http.get_json(
                "blockchain_com",
                f"{BLOCKCHAIN_COM}/unconfirmed-transactions",
                params={"format": "json", "limit": limit},
                ttl=120,
            )
        except ProviderError:
            return []
        known = KNOWN_EXCHANGE_ADDRESSES["bitcoin"]
        flows: list[WhaleFlow] = []
        for tx in (data or {}).get("txs") or []:
            try:
                value_sat = sum(int(o.get("value", 0)) for o in tx.get("out") or [])
                btc = value_sat / 1e8
                if btc < min_btc:
                    continue
                addresses = [str(o.get("addr", "")) for o in tx.get("out") or []]
                counterparty = next(
                    (known[address] for address in addresses if address in known), None
                )
                flows.append(
                    WhaleFlow(
                        chain="bitcoin",
                        tx_hash=tx.get("hash"),
                        amount=btc,
                        amount_usd=0.0,
                        direction="exchange_in" if counterparty else "unknown",  # type: ignore[arg-type]
                        counterparty=counterparty,
                        timestamp=datetime.fromtimestamp(
                            int(tx.get("time", utcnow().timestamp())), tz=timezone.utc
                        ),
                        source="blockchain.info mempool",
                    )
                )
            except Exception:
                continue
        return flows

    async def eth_large_transactions(self, min_eth: float = 1000.0, pages: int = 1) -> list[WhaleFlow]:
        """Blockscout ile son bloklardaki büyük ETH transferlerini tarar."""
        try:
            blocks = await self.http.get_json(
                "blockscout", f"{BLOCKSCOUT_ETH}/blocks", ttl=60
            )
        except ProviderError:
            return []
        items = (blocks or {}).get("items") or []
        flows: list[WhaleFlow] = []
        for block in items[:pages]:
            number = block.get("height")
            if number is None:
                continue
            try:
                data = await self.http.get_json(
                    "blockscout",
                    f"{BLOCKSCOUT_ETH}/blocks/{number}/transactions",
                    ttl=180,
                )
            except ProviderError:
                continue
            for tx in (data or {}).get("items") or []:
                try:
                    value_wei = int(tx.get("value") or 0)
                    eth = value_wei / 1e18
                    if eth < min_eth:
                        continue
                    to_addr = ((tx.get("to") or {}).get("hash") or "").lower()
                    from_addr = ((tx.get("from") or {}).get("hash") or "").lower()
                    known = KNOWN_EXCHANGE_ADDRESSES["ethereum"]
                    if from_addr in known and to_addr not in known:
                        direction = "exchange_out"
                        counterparty = known[from_addr]
                    elif to_addr in known:
                        direction = "exchange_in"
                        counterparty = known[to_addr]
                    else:
                        direction = "unknown"
                        counterparty = None
                    flows.append(
                        WhaleFlow(
                            chain="ethereum",
                            tx_hash=tx.get("hash"),
                            amount=eth,
                            amount_usd=0.0,
                            direction=direction,  # type: ignore[arg-type]
                            counterparty=counterparty,
                            timestamp=datetime.fromtimestamp(
                                int(tx.get("timestamp") or utcnow().timestamp()), tz=timezone.utc
                            ),
                            source="blockscout.com",
                        )
                    )
                except Exception:
                    continue
        return flows

    async def eth_stats(self) -> dict[str, Any] | None:
        try:
            data = await self.http.get_json("blockscout", f"{BLOCKSCOUT_ETH}/stats", ttl=600)
            return data if isinstance(data, dict) else None
        except ProviderError:
            return None
