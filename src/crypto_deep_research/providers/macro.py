"""Makro sağlayıcılar: yfinance (DXY, SPX, altın, VIX), FRED serileri."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from crypto_deep_research.config import Settings
from crypto_deep_research.providers.base import CachedHTTP, ProviderError
from crypto_deep_research.storage.db import Database, stable_key

logger = logging.getLogger(__name__)

FRED = "https://api.stlouisfed.org/fred/series/observations"

YF_TICKERS: dict[str, str] = {
    "DXY": "DX-Y.NYB",
    "SPX": "^GSPC",
    "NASDAQ": "^IXIC",
    "GOLD": "GC=F",
    "SILVER": "SI=F",
    "OIL": "CL=F",
    "VIX": "^VIX",
    "US10Y": "^TNX",
    "COPPER": "HG=F",
}

FRED_SERIES: dict[str, str] = {
    "FEDFUNDS": "Fed fon faizi",
    "DFF": "Fed fon faizi (günlük)",
    "CPIAUCSL": "ABD TUFE",
    "T10Y2Y": "10Y-2Y getiri egrisi",
    "M2SL": "ABD M2 para arzı",
    "UNRATE": "ABD issizlik",
}


class MacroProvider:
    name = "macro"

    def __init__(self, http: CachedHTTP, db: Database, settings: Settings) -> None:
        self.http = http
        self.db = db
        self.settings = settings

    # ------------------------------------------------------------------ yfinance
    async def market_data(self, period: str = "3mo") -> dict[str, dict[str, Any]]:
        """yfinance ile makro varlık getirileri (önbellekli, thread'de)."""
        cache_key = stable_key("yfinance", period, list(YF_TICKERS))
        cached = self.db.cache_get(cache_key)
        if cached and cached[1]:
            return cached[0]

        def _download() -> dict[str, dict[str, Any]]:
            import yfinance as yf

            result: dict[str, dict[str, Any]] = {}
            try:
                data = yf.download(
                    list(YF_TICKERS.values()),
                    period=period,
                    interval="1d",
                    progress=False,
                    threads=True,
                    auto_adjust=True,
                )
            except Exception as exc:
                logger.info("yfinance indirme hatası: %s", exc)
                return result
            if data is None or data.empty:
                return result
            closes = data["Close"] if "Close" in data.columns else data
            for label, ticker in YF_TICKERS.items():
                try:
                    series = closes[ticker].dropna()
                    if series.empty:
                        continue
                    latest = float(series.iloc[-1])
                    first = float(series.iloc[0])
                    week = float(series.iloc[-6]) if len(series) >= 6 else first
                    month = float(series.iloc[-22]) if len(series) >= 22 else first
                    result[label] = {
                        "ticker": ticker,
                        "latest": round(latest, 4),
                        "change_7d_pct": round((latest / week - 1) * 100, 2) if week else None,
                        "change_30d_pct": round((latest / month - 1) * 100, 2) if month else None,
                        "change_period_pct": round((latest / first - 1) * 100, 2) if first else None,
                        "series": [float(v) for v in series.tail(90).tolist()],
                    }
                except Exception:
                    continue
            return result

        result = await asyncio.to_thread(_download)
        if result:
            self.db.cache_set(cache_key, "yfinance", "yf.download", result, 3600, {"period": period})
        return result

    async def history(self, period: str = "2y") -> dict[str, dict[str, float]]:
        """yfinance gunluk kapanis serileri: label -> {ISO tarih: kapanis}."""
        cache_key = stable_key("yfinance_history", period, list(YF_TICKERS))
        cached = self.db.cache_get(cache_key)
        if cached and cached[1]:
            return cached[0]

        def _download() -> dict[str, dict[str, float]]:
            import yfinance as yf

            result: dict[str, dict[str, float]] = {}
            try:
                data = yf.download(
                    list(YF_TICKERS.values()),
                    period=period,
                    interval="1d",
                    progress=False,
                    threads=True,
                    auto_adjust=True,
                )
            except Exception as exc:
                logger.info("yfinance gecmis indirme hatasi: %s", exc)
                return result
            if data is None or data.empty:
                return result
            closes = data["Close"] if "Close" in data.columns else data
            for label, ticker in YF_TICKERS.items():
                try:
                    series = closes[ticker].dropna()
                    result[label] = {
                        index.date().isoformat(): round(float(value), 6)
                        for index, value in series.items()
                    }
                except Exception:
                    continue
            return result

        result = await asyncio.to_thread(_download)
        if result:
            self.db.cache_set(cache_key, "yfinance", "yf.history", result, 21600, {"period": period})
        return result

    # ------------------------------------------------------------------ FRED
    async def fred_series(self, series_id: str, limit: int = 12) -> list[dict[str, Any]]:
        if not self.settings.fred_api_key:
            return []
        try:
            data = await self.http.get_json(
                "fred",
                FRED,
                params={
                    "series_id": series_id,
                    "api_key": self.settings.fred_api_key,
                    "file_type": "json",
                    "sort_order": "desc",
                    "limit": limit,
                },
                ttl=self.settings.ttl_macro,
            )
        except ProviderError:
            return []
        return list((data or {}).get("observations") or [])

    async def fred_dashboard(self) -> dict[str, Any]:
        """Seçili FRED serilerinin son değerleri ve değişimleri."""
        out: dict[str, Any] = {}
        results = await asyncio.gather(
            *[self.fred_series(sid) for sid in FRED_SERIES], return_exceptions=True
        )
        for series_id, rows in zip(FRED_SERIES.keys(), results, strict=False):
            if not isinstance(rows, list) or not rows:
                continue
            values = [(r.get("date"), float(r["value"])) for r in rows if r.get("value") not in (None, ".")]
            if not values:
                continue
            latest_date, latest = values[0]
            previous = values[1][1] if len(values) > 1 else latest
            out[series_id] = {
                "label": FRED_SERIES[series_id],
                "latest": latest,
                "date": latest_date,
                "change": round(latest - previous, 3),
            }
        return out
