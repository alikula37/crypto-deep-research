"""Ortak HTTP istemcisi: TTL önbellek, rate limit, retry ve stale fallback."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from crypto_deep_research.config import Settings
from crypto_deep_research.models import SourceRef, utcnow
from crypto_deep_research.storage.db import Database, stable_key

logger = logging.getLogger(__name__)

# Sağlayıcı başına minimum istek aralığı (saniye). Ücretsiz kotalari korumak için.
MIN_INTERVALS: dict[str, float] = {
    "coingecko": 2.2,
    "binance": 0.2,
    "okx": 0.3,
    "bybit": 0.3,
    "deribit": 0.3,
    "coinalyze": 1.1,
    "defillama": 1.1,
    "cryptopanic": 2.0,
    "gdelt": 1.0,
    "reddit": 2.0,
    "google_trends": 3.0,
    "blockchain_com": 1.0,
    "mempool": 0.5,
    "blockchair": 2.0,
    "etherscan": 0.4,
    "yfinance": 1.0,
    "fred": 1.0,
    "rss": 0.5,
    "alternative_me": 1.0,
    "default": 0.5,
}


class ProviderError(RuntimeError):
    """Bir sağlayıcıdan veri alınamadığında firlatilir."""

    def __init__(self, provider: str, message: str, url: str | None = None) -> None:
        self.provider = provider
        self.url = url
        super().__init__(f"[{provider}] {message}")


class RateLimiter:
    """Basit, async, ardisik istekleri aralayan limiter."""

    def __init__(self, min_interval: float) -> None:
        self.min_interval = max(0.0, min_interval)
        self._last = 0.0
        self._lock: asyncio.Lock | None = None

    async def acquire(self) -> None:
        if self._lock is None:
            self._lock = asyncio.Lock()
        async with self._lock:
            now = time.monotonic()
            wait = self._last + self.min_interval - now
            if wait > 0:
                await asyncio.sleep(wait)
            self._last = time.monotonic()


class CachedHTTP:
    """httpx tabanlı, SQLite önbellekli HTTP istemcisi."""

    def __init__(self, db: Database, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self._client: httpx.AsyncClient | None = None
        self._client_lock: asyncio.Lock | None = None
        self._limiters: dict[str, RateLimiter] = {}

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            if self._client_lock is None:
                self._client_lock = asyncio.Lock()
            async with self._client_lock:
                if self._client is None:
                    self._client = httpx.AsyncClient(
                        timeout=self.settings.http_timeout,
                        headers={"User-Agent": self.settings.user_agent},
                        follow_redirects=True,
                    )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _limiter(self, provider: str) -> RateLimiter:
        if provider not in self._limiters:
            self._limiters[provider] = RateLimiter(
                MIN_INTERVALS.get(provider, MIN_INTERVALS["default"])
            )
        return self._limiters[provider]

    async def get_json(
        self,
        provider: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        ttl: int = 300,
        allow_stale: bool = True,
        limiter: bool = True,
    ) -> Any:
        """JSON getirir; TTL içindeyse önbellekten, hata durumunda stale önbellekten döner."""
        params = params or {}
        cache_key = stable_key(provider, url, params)
        cached = self.db.cache_get(cache_key)
        if cached and cached[1]:
            logger.debug("cache hit (fresh) %s %s", provider, url)
            return cached[0]

        client = await self._get_client()
        last_error: Exception | None = None
        for attempt in range(self.settings.http_retries):
            try:
                if limiter:
                    await self._limiter(provider).acquire()
                response = await client.get(url, params=params, headers=headers)
                if response.status_code == 429:
                    wait = 2.0 * (attempt + 1)
                    logger.warning("%s 429 aldi, %.1fs bekleniyor", provider, wait)
                    await asyncio.sleep(wait)
                    continue
                response.raise_for_status()
                payload = response.json()
                self.db.cache_set(cache_key, provider, url, payload, ttl, params)
                return payload
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                if attempt < self.settings.http_retries - 1:
                    await asyncio.sleep(1.0 * (attempt + 1))
        if cached and allow_stale:
            logger.warning("%s başarısız, stale önbellek kullanıliyor: %s", provider, url)
            return cached[0]
        raise ProviderError(provider, str(last_error), url)

    async def get_text(
        self,
        provider: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        ttl: int = 600,
        allow_stale: bool = True,
    ) -> str:
        params = params or {}
        cache_key = stable_key(provider, url, params)
        cached = self.db.cache_get(cache_key)
        if cached and cached[1]:
            return cached[0]

        client = await self._get_client()
        last_error: Exception | None = None
        for attempt in range(self.settings.http_retries):
            try:
                await self._limiter(provider).acquire()
                response = await client.get(url, params=params, headers=headers)
                response.raise_for_status()
                text = response.text
                self.db.cache_set(cache_key, provider, url, text, ttl, params)
                return text
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                if attempt < self.settings.http_retries - 1:
                    await asyncio.sleep(1.0 * (attempt + 1))
        if cached and allow_stale:
            return cached[0]
        raise ProviderError(provider, str(last_error), url)


def source(
    name: str,
    url: str | None = None,
    kind: str = "api",
    note: str | None = None,
) -> SourceRef:
    return SourceRef(name=name, url=url, kind=kind, fetched_at=utcnow(), note=note)  # type: ignore[arg-type]


def estimate_tokens(text: str) -> int:
    """Kaba token tahmini (~4 karakter/token)."""
    return max(1, len(text) // 4)
