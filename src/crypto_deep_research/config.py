"""Uygulama ayarlari."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Ortam degiskenleri ile yapilandirilir (CDR_ oneki)."""

    model_config = SettingsConfigDict(env_prefix="CDR_", env_file=".env", extra="ignore")

    data_dir: Path = Field(default=Path("data"))

    # Ucretsiz API anahtarlari (opsiyonel)
    coingecko_api_key: str | None = None
    coinalyze_api_key: str | None = None
    cryptopanic_api_key: str | None = None
    etherscan_api_key: str | None = None
    fred_api_key: str | None = None

    # LLM (opsiyonel)
    openrouter_api_key: str | None = None
    openrouter_model: str = "openrouter/auto"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_timeout: float = 120.0

    # Yerel embedding
    embedding_model: str = "intfloat/multilingual-e5-large"
    embedding_dim: int = 1024
    embeddings_enabled: bool = True

    # Ag
    http_timeout: float = 30.0
    http_retries: int = 3
    user_agent: str = "crypto-deep-research/0.1 (+https://github.com/alikula37/crypto-deep-research)"

    # Onbellek TTL varsayilanlari (saniye)
    ttl_price: int = 60
    ttl_market: int = 300
    ttl_ohlcv: int = 300
    ttl_derivatives: int = 180
    ttl_news: int = 600
    ttl_sentiment: int = 900
    ttl_onchain: int = 900
    ttl_macro: int = 3600
    ttl_static: int = 86400

    @property
    def db_path(self) -> Path:
        return self.data_dir / "crypto.db"

    @property
    def vector_dir(self) -> Path:
        return self.data_dir / "vectors"

    @property
    def reports_dir(self) -> Path:
        return self.data_dir / "reports"

    @property
    def prompts_dir(self) -> Path:
        return self.data_dir / "prompts"

    def ensure_dirs(self) -> None:
        for path in (self.data_dir, self.reports_dir, self.prompts_dir, self.vector_dir):
            path.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings
