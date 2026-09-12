"""Borsa sağlayıcıları: Binance, OKX, Bybit, Deribit (public REST)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from crypto_deep_research.config import Settings
from crypto_deep_research.models import Kline, utcnow
from crypto_deep_research.providers.base import CachedHTTP, ProviderError

logger = logging.getLogger(__name__)

BINANCE_SPOT = "https://api.binance.com"
BINANCE_FUTURES = "https://fapi.binance.com"
OKX = "https://www.okx.com"
BYBIT = "https://api.bybit.com"
DERIBIT = "https://www.deribit.com/api/v2/public"

BINANCE_INTERVALS = {
    "1m": "1m",
    "3m": "3m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "1h",
    "2h": "2h",
    "4h": "4h",
    "6h": "6h",
    "8h": "8h",
    "12h": "12h",
    "1d": "1d",
    "3d": "3d",
    "1w": "1w",
    "1M": "1M",
}

# Binance futures'ta 1000x carpanli listelenen kontratlar
PERP_SYMBOL_OVERRIDES: dict[str, str] = {
    "PEPE": "1000PEPEUSDT",
    "SHIB": "1000SHIBUSDT",
    "BONK": "1000BONKUSDT",
    "FLOKI": "1000FLOKIUSDT",
    "LUNC": "1000LUNCUSDT",
    "XEC": "1000XECUSDT",
    "SATS": "1000SATSUSDT",
    "RATS": "1000RATSUSDT",
    "CHEEMS": "1000CHEEMSUSDT",
    "X": "1000XUSDT",
}


class ExchangeProvider:
    """Binance ağırlıklı, çoklu borsa public veri sağlayıcısi."""

    def __init__(self, http: CachedHTTP, settings: Settings) -> None:
        self.http = http
        self.settings = settings

    # ------------------------------------------------------------------ Binance
    def _binance_symbol(self, symbol: str) -> str:
        symbol = symbol.upper()
        return symbol if symbol.endswith("USDT") else f"{symbol}USDT"

    def perp_symbol(self, symbol: str) -> str:
        """Binance futures sembolu; 1000x carpanli kontratlari da kapsar."""
        token = symbol.upper()
        if token in PERP_SYMBOL_OVERRIDES:
            return PERP_SYMBOL_OVERRIDES[token]
        return self._binance_symbol(token)

    @staticmethod
    def perp_multiplier(perp_symbol: str) -> float:
        return 1000.0 if perp_symbol.startswith("1000") else 1.0

    async def klines(
        self, symbol: str, interval: str = "1d", limit: int = 500, quote: str | None = "USDT"
    ) -> list[Kline]:
        if interval not in BINANCE_INTERVALS:
            interval = "1d"
        pair = self._binance_symbol(symbol) if quote else symbol.upper()
        data = await self.http.get_json(
            "binance",
            f"{BINANCE_SPOT}/api/v3/klines",
            params={
                "symbol": pair,
                "interval": interval,
                "limit": min(limit, 1000),
            },
            ttl=self.settings.ttl_ohlcv,
        )
        klines: list[Kline] = []
        for row in data or []:
            try:
                klines.append(
                    Kline(
                        ts=datetime.fromtimestamp(int(row[0]) / 1000, tz=timezone.utc),
                        open=float(row[1]),
                        high=float(row[2]),
                        low=float(row[3]),
                        close=float(row[4]),
                        volume=float(row[5]),
                    )
                )
            except (IndexError, ValueError, TypeError):
                continue
        return klines

    async def binance_ticker(self, symbol: str) -> dict[str, Any]:
        return await self.http.get_json(
            "binance",
            f"{BINANCE_SPOT}/api/v3/ticker/24hr",
            params={"symbol": self._binance_symbol(symbol)},
            ttl=self.settings.ttl_price,
        )

    async def binance_funding(self, symbol: str, perp_symbol: str | None = None) -> float | None:
        try:
            data = await self.http.get_json(
                "binance",
                f"{BINANCE_FUTURES}/fapi/v1/premiumIndex",
                params={"symbol": perp_symbol or self.perp_symbol(symbol)},
                ttl=self.settings.ttl_derivatives,
            )
            return float(data.get("lastFundingRate"))
        except (ProviderError, ValueError, TypeError):
            return None

    async def binance_open_interest(
        self, symbol: str, perp_symbol: str | None = None
    ) -> float | None:
        try:
            data = await self.http.get_json(
                "binance",
                f"{BINANCE_FUTURES}/fapi/v1/openInterest",
                params={"symbol": perp_symbol or self.perp_symbol(symbol)},
                ttl=self.settings.ttl_derivatives,
            )
            return float(data.get("openInterest"))
        except (ProviderError, ValueError, TypeError):
            return None

    async def binance_long_short_ratio(
        self, symbol: str, period: str = "1h", perp_symbol: str | None = None
    ) -> float | None:
        try:
            data = await self.http.get_json(
                "binance",
                f"{BINANCE_FUTURES}/futures/data/globalLongShortAccountRatio",
                params={
                    "symbol": perp_symbol or self.perp_symbol(symbol),
                    "period": period,
                    "limit": 1,
                },
                ttl=self.settings.ttl_derivatives,
            )
            if data:
                return float(data[-1].get("longShortRatio"))
        except (ProviderError, ValueError, TypeError):
            pass
        return None

    async def binance_order_book(self, symbol: str, limit: int = 500) -> dict[str, Any]:
        return await self.http.get_json(
            "binance",
            f"{BINANCE_SPOT}/api/v3/depth",
            params={"symbol": self._binance_symbol(symbol), "limit": min(limit, 500)},
            ttl=self.settings.ttl_derivatives,
        )

    # ------------------------------------------------------------------ OKX
    async def okx_ticker(self, symbol: str) -> dict[str, Any] | None:
        try:
            data = await self.http.get_json(
                "okx",
                f"{OKX}/api/v5/market/ticker",
                params={"instId": f"{symbol.upper()}-USDT"},
                ttl=self.settings.ttl_price,
            )
            return (data.get("data") or [None])[0]
        except ProviderError:
            return None

    # ------------------------------------------------------------------ Bybit
    async def bybit_ticker(self, symbol: str) -> dict[str, Any] | None:
        try:
            data = await self.http.get_json(
                "bybit",
                f"{BYBIT}/v5/market/tickers",
                params={"category": "spot", "symbol": f"{symbol.upper()}USDT"},
                ttl=self.settings.ttl_price,
            )
            result = (data.get("result") or {}).get("list") or []
            return result[0] if result else None
        except ProviderError:
            return None

    async def multi_exchange_tickers(self, symbol: str) -> dict[str, dict[str, Any]]:
        """Binance, OKX ve Bybit için anlık hacim/fiyat özeti."""
        out: dict[str, dict[str, Any]] = {}
        try:
            binance = await self.binance_ticker(symbol)
            out["Binance"] = {
                "price_usd": float(binance.get("lastPrice", 0) or 0),
                "volume_24h_usd": float(binance.get("quoteVolume", 0) or 0),
                "change_24h_pct": float(binance.get("priceChangePercent", 0) or 0),
                "trades_24h": int(binance.get("count", 0) or 0),
            }
        except (ProviderError, ValueError, TypeError):
            pass
        okx = await self.okx_ticker(symbol)
        if okx:
            try:
                out["OKX"] = {
                    "price_usd": float(okx.get("last", 0) or 0),
                    "volume_24h_usd": float(okx.get("volCcy24h", 0) or 0),
                    "change_24h_pct": None,
                    "trades_24h": None,
                }
            except (ValueError, TypeError):
                pass
        bybit = await self.bybit_ticker(symbol)
        if bybit:
            try:
                out["Bybit"] = {
                    "price_usd": float(bybit.get("lastPrice", 0) or 0),
                    "volume_24h_usd": float(bybit.get("turnover24h", 0) or 0),
                    "change_24h_pct": float(bybit.get("price24hPcnt", 0) or 0) * 100,
                    "trades_24h": None,
                }
            except (ValueError, TypeError):
                pass
        return out

    # ------------------------------------------------------------------ Deribit
    async def deribit_dvol(self, currency: str = "BTC") -> dict[str, Any] | None:
        """Deribit volatilite endeksi (DVOL) son değeri."""
        try:
            now_ms = int(utcnow().timestamp() * 1000)
            data = await self.http.get_json(
                "deribit",
                f"{DERIBIT}/get_volatility_index_data",
                params={
                    "currency": currency.upper(),
                    "start_timestamp": now_ms - 7 * 86400 * 1000,
                    "end_timestamp": now_ms,
                    "resolution": "3600",
                },
                ttl=self.settings.ttl_derivatives,
            )
            rows = (data.get("result") or {}).get("data") or []
            if not rows:
                return None
            closes = [float(r[4]) for r in rows if r and len(r) >= 5]
            if not closes:
                return None
            return {
                "current": closes[-1],
                "min_7d": min(closes),
                "max_7d": max(closes),
                "change_7d": closes[-1] - closes[0],
                "source": "Deribit DVOL",
            }
        except (ProviderError, ValueError, TypeError, KeyError):
            return None
