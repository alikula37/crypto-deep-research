"""Ortak veri modelleri."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CoinRef(BaseModel):
    """Coin kimligi (CoinGecko id + sembol)."""

    id: str = Field(description="CoinGecko id, orn. bitcoin")
    symbol: str = Field(description="Sembol, orn. btc")
    name: str = Field(description="Görünen ad, orn. Bitcoin")


class SourceRef(BaseModel):
    """Bir verinin kaynağı."""

    name: str
    url: str | None = None
    kind: Literal["api", "rss", "page", "computed", "cache"] = "api"
    fetched_at: datetime | None = None
    note: str | None = None


class Kline(BaseModel):
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class MarketSnapshot(BaseModel):
    coin: CoinRef
    price_usd: float
    market_cap_usd: float | None = None
    fully_diluted_valuation_usd: float | None = None
    rank: int | None = None
    volume_24h_usd: float | None = None
    change_1h_pct: float | None = None
    change_24h_pct: float | None = None
    change_7d_pct: float | None = None
    change_30d_pct: float | None = None
    ath_usd: float | None = None
    ath_date: datetime | None = None
    ath_change_pct: float | None = None
    atl_usd: float | None = None
    atl_date: datetime | None = None
    atl_change_pct: float | None = None
    circulating_supply: float | None = None
    total_supply: float | None = None
    max_supply: float | None = None
    categories: list[str] = Field(default_factory=list)
    fetched_at: datetime = Field(default_factory=utcnow)

    @property
    def distance_from_ath_pct(self) -> float | None:
        if not self.ath_usd or not self.price_usd:
            return None
        return (self.price_usd / self.ath_usd - 1.0) * 100.0

    @property
    def distance_from_atl_pct(self) -> float | None:
        if not self.atl_usd or not self.price_usd:
            return None
        return (self.price_usd / self.atl_usd - 1.0) * 100.0


class GlobalMarket(BaseModel):
    total_market_cap_usd: float | None = None
    total_volume_usd: float | None = None
    btc_dominance: float | None = None
    eth_dominance: float | None = None
    market_cap_change_24h_pct: float | None = None
    active_cryptocurrencies: int | None = None
    fetched_at: datetime = Field(default_factory=utcnow)


class NewsArticle(BaseModel):
    title: str
    url: str
    source: str
    published_at: datetime | None = None
    summary: str | None = None
    currencies: list[str] = Field(default_factory=list)
    sentiment_raw: float | None = Field(default=None, description="Kaynağın doğrudan sentiment değeri")
    sentiment: float | None = Field(
        default=None, description="Hesaplanan sentiment -1 (negatif) .. 1 (pozitif)"
    )
    votes_positive: int | None = None
    votes_negative: int | None = None
    panic_score: float | None = None
    language: str = "en"

    def text_for_embedding(self) -> str:
        parts = [self.title]
        if self.summary:
            parts.append(self.summary)
        parts.append(f"Kaynak: {self.source}")
        return "\n".join(parts)


class FearGreed(BaseModel):
    value: int
    classification: str
    timestamp: datetime | None = None
    source: str = "alternative.me"


class DerivativesSnapshot(BaseModel):
    symbol: str
    open_interest_usd: float | None = None
    open_interest_change_24h_pct: float | None = None
    funding_rate: float | None = None
    long_short_ratio: float | None = None
    liquidations_24h_long_usd: float | None = None
    liquidations_24h_short_usd: float | None = None
    source: str | None = None
    fetched_at: datetime = Field(default_factory=utcnow)


class WhaleFlow(BaseModel):
    chain: str
    tx_hash: str | None = None
    amount: float = 0.0
    amount_usd: float = 0.0
    direction: Literal["exchange_in", "exchange_out", "unknown", "mint", "burn"] = "unknown"
    counterparty: str | None = None
    timestamp: datetime | None = None
    source: str | None = None


class AnalysisResult(BaseModel):
    """Tek bir analiz modulunun sonuçu."""

    key: str
    title: str
    status: Literal["ok", "partial", "no_data", "error"] = "ok"
    summary: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    sources: list[SourceRef] = Field(default_factory=list)
    score: float | None = Field(default=None, description="Piyasa etkisi -1..1")
    confidence: float = 0.0
    warnings: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=utcnow)


class ItemResult(AnalysisResult):
    """66 maddelik araştırma listesindeki bir maddenin sonuçu."""

    item_id: int
    title_tr: str = ""
    category: str = ""
    weight: float = 1.0
    qualitative: bool = False


class ResearchRun(BaseModel):
    run_id: str
    coin: CoinRef
    created_at: datetime = Field(default_factory=utcnow)
    timeframe: str = "1d"
    lookback_days: int = 365
    platform: str | None = None
    analyses: list[str] = Field(default_factory=list)
    items: list[ItemResult] = Field(default_factory=list)
    weighted_score: float | None = None
    up_probability: float | None = None
    down_probability: float | None = None
    expected_low: float | None = None
    expected_high: float | None = None
    current_price: float | None = None
    sources: list[SourceRef] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


ContextState = Literal["hot", "compressed", "offloaded", "dropped"]
PolicyAction = Literal[
    "KEEP", "COMPRESS", "CACHE", "OFFLOAD", "DROP", "PIN", "PREFETCH"
]


class ContextObject(BaseModel):
    """Yönetilen context birimi (Context Control Plane).

    Her context objesinin kimligi, scope'u, provenance'i, TTL'i ve versiyonu vardir.
    """

    key: str
    kind: Literal["analysis", "news", "research_item", "report", "chat"] = "analysis"
    scope: dict[str, str] = Field(default_factory=dict)
    content: str = ""
    blob_ref: str | None = Field(
        default=None, description="Offload edilen tam verinin SQLite anahtari"
    )
    data: dict[str, Any] = Field(default_factory=dict)
    provenance: list[SourceRef] = Field(default_factory=list)
    ttl_seconds: int | None = None
    version: int = 1
    tokens_estimate: int = 0
    priority: float = 1.0
    pinned: bool = False
    state: ContextState = "hot"
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class RetrievedContext(BaseModel):
    key: str
    content: str
    score: float
    source: str | None = None
    coin: str | None = None
    kind: str | None = None
    timestamp: datetime | None = None
