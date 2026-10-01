"""Uygulama ayarlari."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Ortam değişkenleri ile yapılandırılır (CDR_ oneki)."""

    model_config = SettingsConfigDict(env_prefix="CDR_", env_file=".env", extra="ignore")

    data_dir: Path = Field(default=Path("data"))
    state_dir: Path | None = Field(
        default=None,
        description="SQLite ve vektor deposu icin ic durum dizini (varsayilan: data_dir). "
        "Docker'da WAL guvenligi icin konteyner ici kalici birime isaret edilmelidir.",
    )

    # Ücretsiz API anahtarlari (opsiyonel)
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
    rag_reranker_model: str | None = None

    # Ag
    http_timeout: float = 30.0
    http_retries: int = 3
    user_agent: str = "crypto-deep-research/0.1 (+https://github.com/alikula37/crypto-deep-research)"

    # Önbellek TTL varsayılanları (saniye)
    ttl_price: int = 60
    ttl_market: int = 300
    ttl_ohlcv: int = 300
    ttl_derivatives: int = 180
    ttl_news: int = 600
    ttl_sentiment: int = 900
    ttl_onchain: int = 900
    ttl_macro: int = 3600
    ttl_static: int = 86400

    # Takip listesi (watchlist) otomatik kosulari
    watchlist_enabled: bool = True
    watchlist_interval_minutes: int = 60
    watchlist_auto_run_hours: int = 24

    # Telegram botu (opsiyonel)
    telegram_token: str | None = None
    telegram_chat_id: str | None = None
    telegram_autostart: bool = False

    # Ogrenme dongusu (ozellik kaydi + outcome etiketleme)
    learning_enabled: bool = True
    outcome_interval_minutes: int = 60
    outcome_max_attempts: int = 14
    watchlist_seed: bool = True
    drift_window_days: int = 30
    drift_baseline_days: int = 90
    cache_prune_days: int = 7
    archive_runs_days: int = 540

    @property
    def effective_state_dir(self) -> Path:
        return self.state_dir or self.data_dir

    @property
    def db_path(self) -> Path:
        return self.effective_state_dir / "crypto.db"

    @property
    def vector_dir(self) -> Path:
        return self.effective_state_dir / "vectors"

    @property
    def reports_dir(self) -> Path:
        return self.data_dir / "reports"

    @property
    def prompts_dir(self) -> Path:
        return self.data_dir / "prompts"

    def ensure_dirs(self) -> None:
        for path in (
            self.data_dir,
            self.reports_dir,
            self.prompts_dir,
            self.effective_state_dir,
            self.vector_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings
