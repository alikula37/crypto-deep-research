"""Opsiyonel OpenRouter istemcisi (anahtar yoksa yalnızca prompt üretilir)."""

from __future__ import annotations

import logging

import httpx

from crypto_deep_research.config import Settings

logger = logging.getLogger(__name__)


class OpenRouterError(RuntimeError):
    pass


class OpenRouterClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def enabled(self) -> bool:
        return bool(self.settings.openrouter_api_key)

    async def complete(
        self,
        prompt: str,
        *,
        model: str | None = None,
        system: str | None = None,
        max_tokens: int = 4000,
        temperature: float = 0.3,
    ) -> str:
        if not self.enabled:
            raise OpenRouterError("OpenRouter API anahtari tanımli değil (CDR_OPENROUTER_API_KEY).")
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        payload = {
            "model": model or self.settings.openrouter_model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        headers = {
            "Authorization": f"Bearer {self.settings.openrouter_api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/alikula37/crypto-deep-research",
            "X-Title": "crypto-deep-research",
        }
        async with httpx.AsyncClient(timeout=self.settings.openrouter_timeout) as client:
            response = await client.post(
                f"{self.settings.openrouter_base_url}/chat/completions",
                json=payload,
                headers=headers,
            )
            if response.status_code >= 400:
                raise OpenRouterError(f"OpenRouter hata {response.status_code}: {response.text[:400]}")
            data = response.json()
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise OpenRouterError(f"Beklenmeyen OpenRouter yaniti: {data}") from exc
