"""MCP server: Claude, Codex, Cursor gibi araçlara veri ve analiz sunar."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from mcp.server.mcpserver import MCPServer

from crypto_deep_research.analysis.base import AnalysisContext
from crypto_deep_research.analysis.engine import run_analyses
from crypto_deep_research.config import get_settings
from crypto_deep_research.deep_research.engine import DeepResearchEngine
from crypto_deep_research.deep_research.registry import registry_summary
from crypto_deep_research.models import Kline
from crypto_deep_research.providers.registry import build_providers
from crypto_deep_research.rag.engine import RAGEngine
from crypto_deep_research.storage.db import Database

server = MCPServer(
    name="crypto-deep-research",
    instructions=(
        "Kripto paralar için ücretsiz veri kaynaklarından beslenen analiz, RAG ve 66 maddelik "
        "deep research araçlari sunar. Skorlar -1 (negatif) ile +1 (pozitif) arasındadir; "
        "yatırım tavsiyesi değildir."
    ),
    version="0.2.0",
)


def _context():
    settings = get_settings()
    db = Database(settings.db_path)
    providers = build_providers(settings, db)
    return settings, db, providers


@server.tool()
def list_analyses() -> list[dict[str, str]]:
    """Kullanılabilir analiz anahtarlarini listeler."""
    from crypto_deep_research.analysis.engine import available_analyses

    return available_analyses()


@server.tool()
def list_research_items() -> list[dict[str, Any]]:
    """66 maddelik araştırma listesini döndürür."""
    return registry_summary()


@server.tool()
async def resolve_coin(query: str) -> dict[str, str]:
    """Sembol veya isimden coin kimligini (CoinGecko id) cozer."""
    settings, db, providers = _context()
    try:
        ref = await providers.coingecko.resolve(query)
        return ref.model_dump()
    finally:
        await providers.aclose()


@server.tool()
async def get_market_snapshot(coin: str) -> dict[str, Any]:
    """Anlık fiyat, piyasa değeri, ATH/ATL mesafesi ve değişimleri döndürür."""
    settings, db, providers = _context()
    try:
        ref = await providers.coingecko.resolve(coin)
        snapshot = await providers.coingecko.snapshot(ref)
        global_market = await providers.coingecko.global_market()
        return {
            "snapshot": snapshot.model_dump(mode="json"),
            "global": global_market.model_dump(mode="json"),
        }
    finally:
        await providers.aclose()


@server.tool()
async def run_analysis(
    coin: str, analysis: str = "technical", timeframe: str = "1d", lookback_days: int = 365
) -> dict[str, Any]:
    """Tek bir analizi çalıştırir (ornek: technical, liquidations, news, volumes, whales...)."""
    settings, db, providers = _context()
    try:
        ref = await providers.coingecko.resolve(coin)
        ctx = AnalysisContext(
            coin=ref,
            providers=providers,
            settings=settings,
            timeframe=timeframe,
            lookback_days=lookback_days,
        )
        results = await run_analyses(ctx, [analysis])
        return results[0].model_dump(mode="json") if results else {"error": "analiz yok"}
    finally:
        await providers.aclose()


@server.tool()
async def get_price_chart(
    coin: str, timeframe: str = "1d", limit: int = 200
) -> dict[str, Any]:
    """Timeframe bazlı OHLCV mum verisi döndürür (grafik/araçlar için).

    timeframe: 15m, 30m, 1h, 4h, 1d, 1w. Yedek olarak CoinGecko kapanış serisi kullanılır.
    """
    settings, db, providers = _context()
    try:
        ref = await providers.coingecko.resolve(coin)
        limit = min(max(limit, 30), 1000)
        klines = await providers.exchange.klines(ref.symbol, timeframe, limit)
        source = "Binance"
        if not klines:
            days_map = {"15m": 1, "30m": 1, "1h": 7, "4h": 14, "1d": 90, "1w": 365}
            chart = await providers.coingecko.market_chart(
                ref.id, days=days_map.get(timeframe, 90)
            )
            prices = [pair for pair in chart.get("prices") or [] if pair and pair[1]]
            klines = [
                Kline(
                    ts=datetime.fromtimestamp(pair[0] / 1000, tz=timezone.utc),
                    open=float(pair[1]),
                    high=float(pair[1]),
                    low=float(pair[1]),
                    close=float(pair[1]),
                    volume=0.0,
                )
                for pair in prices[-limit:]
            ]
            source = "CoinGecko (kapanış fiyatları)"
        return {
            "coin": ref.model_dump(),
            "timeframe": timeframe,
            "source": source,
            "count": len(klines),
            "candles": [
                {
                    "t": kline.ts.isoformat(),
                    "o": kline.open,
                    "h": kline.high,
                    "l": kline.low,
                    "c": kline.close,
                    "v": kline.volume,
                }
                for kline in klines
            ],
        }
    finally:
        await providers.aclose()


@server.tool()
async def deep_research(
    coin: str,
    timeframe: str = "1d",
    lookback_days: int = 365,
    platform: str = "generic",
    profile: str = "balanced",
    language: str = "tr",
    include_prompt: bool = False,
) -> dict[str, Any]:
    """66 maddelik araştırmayı çalıştırir; skor, olasılık, rapor ve prompt üretir.

    profile: balanced | conservative (dogrulanmis veri agirlikli) | aggressive (momentum agirlikli)
    language: tr | en (prompt yanit dili)
    """
    settings, db, providers = _context()
    engine = DeepResearchEngine(providers, settings, db)
    try:
        output = await engine.run(
            coin,
            timeframe=timeframe,
            lookback_days=lookback_days,
            platform=platform,
            profile=profile,
            language=language,
        )
        run = output.run
        response: dict[str, Any] = {
            "run_id": run.run_id,
            "coin": run.coin.model_dump(),
            "created_at": run.created_at.isoformat(),
            "current_price": run.current_price,
            "weighted_score": run.weighted_score,
            "up_probability": run.up_probability,
            "down_probability": run.down_probability,
            "expected_range": [run.expected_low, run.expected_high],
            "top_positive_items": [
                {"id": item.item_id, "title": item.title_tr, "score": item.score}
                for item in sorted(
                    [i for i in run.items if i.score is not None], key=lambda i: i.score, reverse=True
                )[:5]
            ],
            "top_negative_items": [
                {"id": item.item_id, "title": item.title_tr, "score": item.score}
                for item in sorted(
                    [i for i in run.items if i.score is not None], key=lambda i: i.score
                )[:5]
            ],
            "report_path": output.report_path,
            "prompt_path": output.prompt_path,
            "notes": run.notes,
        }
        if include_prompt:
            response["prompt"] = output.prompt
        return response
    finally:
        await providers.aclose()


@server.tool()
def search_context(query: str, coin: str | None = None, k: int = 8) -> list[dict[str, Any]]:
    """Yerel RAG deposunda (haber, analiz, rapor) arama yapar."""
    settings = get_settings()
    db = Database(settings.db_path)
    engine = RAGEngine(db, settings)
    results = engine.search(query, coin=coin, k=k)
    return [result.model_dump(mode="json") for result in results]


@server.tool()
def list_reports(limit: int = 20) -> list[dict[str, Any]]:
    """Üretilmiş raporlari listeler."""
    settings = get_settings()
    db = Database(settings.db_path)
    return db.list_reports(limit=limit)


@server.tool()
def get_report(name: str) -> dict[str, Any]:
    """Rapor adiyla markdown icerigini dondurur."""
    settings = get_settings()
    db = Database(settings.db_path)
    report = db.get_report(name)
    if report:
        return {"name": report["name"], "coin": report["coin"], "markdown": report["markdown"]}
    path = settings.reports_dir / f"{name}.md"
    if not path.exists():
        return {"error": "rapor bulunamadi"}
    return {
        "name": name,
        "coin": name.split("_")[0].lower(),
        "markdown": path.read_text(encoding="utf-8"),
    }


@server.tool()
def get_run(run_id: str) -> dict[str, Any]:
    """Kosu detaylarıni (66 madde sonuçları dahil) döndürür."""
    settings = get_settings()
    db = Database(settings.db_path)
    run = db.get_run(run_id)
    if not run:
        return {"error": "kosu bulunamadı"}
    return json.loads(run.model_dump_json())


def run_stdio() -> None:
    server.run("stdio")


def run_sse() -> None:
    server.run("sse")


if __name__ == "__main__":
    run_stdio()
