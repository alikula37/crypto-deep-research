"""Coinalyze sağlayıcısi: likidasyon, open interest, funding, long/short (ücretsiz key)."""

from __future__ import annotations

import logging
import time
from typing import Any

from crypto_deep_research.config import Settings
from crypto_deep_research.providers.base import CachedHTTP, ProviderError

logger = logging.getLogger(__name__)

BASE = "https://api.coinalyze.net/v1"


class CoinalyzeProvider:
    """Ücretsiz API anahtari ile çalışır; anahtar yoksa bos sonuç döner."""

    name = "coinalyze"

    def __init__(self, http: CachedHTTP, settings: Settings) -> None:
        self.http = http
        self.settings = settings

    @property
    def enabled(self) -> bool:
        return bool(self.settings.coinalyze_api_key)

    def _symbol(self, symbol: str) -> str:
        return f"{symbol.upper()}USDT_PERP.A"

    async def _get(self, path: str, params: dict[str, Any], ttl: int) -> Any:
        if not self.enabled:
            raise ProviderError(self.name, "Coinalyze API anahtari tanımli değil")
        params = {**params, "api_key": self.settings.coinalyze_api_key}
        return await self.http.get_json(self.name, f"{BASE}{path}", params=params, ttl=ttl)

    async def liquidation_history(self, symbol: str, hours: int = 24) -> list[dict[str, Any]]:
        now = int(time.time())
        data = await self._get(
            "/liquidation-history",
            {
                "symbols": self._symbol(symbol),
                "interval": "1hour",
                "from": now - hours * 3600,
                "to": now,
                "convert_to_usd": "true",
            },
            ttl=self.settings.ttl_derivatives,
        )
        if not data:
            return []
        history = (data[0] or {}).get("history") or []
        return history

    async def open_interest_history(self, symbol: str, hours: int = 72) -> list[dict[str, Any]]:
        now = int(time.time())
        data = await self._get(
            "/open-interest-history",
            {
                "symbols": self._symbol(symbol),
                "interval": "1hour",
                "from": now - hours * 3600,
                "to": now,
                "convert_to_usd": "true",
            },
            ttl=self.settings.ttl_derivatives,
        )
        if not data:
            return []
        return (data[0] or {}).get("history") or []

    async def funding_history(self, symbol: str, hours: int = 72) -> list[dict[str, Any]]:
        now = int(time.time())
        data = await self._get(
            "/funding-rate-history",
            {
                "symbols": self._symbol(symbol),
                "interval": "1hour",
                "from": now - hours * 3600,
                "to": now,
            },
            ttl=self.settings.ttl_derivatives,
        )
        if not data:
            return []
        return (data[0] or {}).get("history") or []

    async def long_short_history(self, symbol: str, hours: int = 48) -> list[dict[str, Any]]:
        now = int(time.time())
        data = await self._get(
            "/long-short-ratio-history",
            {
                "symbols": self._symbol(symbol),
                "interval": "1hour",
                "from": now - hours * 3600,
                "to": now,
            },
            ttl=self.settings.ttl_derivatives,
        )
        if not data:
            return []
        return (data[0] or {}).get("history") or []
