"""MCP server: Claude, Codex, Cursor gibi araclara veri ve analiz sunar."""

from __future__ import annotations

import json
from typing import Any

from mcp.server.mcpserver import MCPServer

from crypto_deep_research.analysis.base import AnalysisContext
from crypto_deep_research.analysis.engine import run_analyses
from crypto_deep_research.config import get_settings
from crypto_deep_research.deep_research.engine import DeepResearchEngine
from crypto_deep_research.deep_research.registry import registry_summary
from crypto_deep_research.providers.registry import build_providers
from crypto_deep_research.rag.engine import RAGEngine
from crypto_deep_research.storage.db import Database

server = MCPServer(
    name="crypto-deep-research",
    instructions=(
        "Kripto paralar icin ucretsiz veri kaynaklarindan beslenen analiz, RAG ve 66 maddelik "
        "deep research araclari sunar. Skorlar -1 (negatif) ile +1 (pozitif) arasindadir; "
        "yatirim tavsiyesi degildir."
    ),
    version="0.1.0",
)


def _context():
    settings = get_settings()
    db = Database(settings.db_path)
    providers = build_providers(settings, db)
    return settings, db, providers


@server.tool()
def list_analyses() -> list[dict[str, str]]:
    """Kullanilabilir analiz anahtarlarini listeler."""
    from crypto_deep_research.analysis.engine import available_analyses

    return available_analyses()


@server.tool()
def list_research_items() -> list[dict[str, Any]]:
    """66 maddelik arastirma listesini dondurur."""
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
    """Anlik fiyat, piyasa degeri, ATH/ATL mesafesi ve degisimleri dondurur."""
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
    """Tek bir analizi calistirir (ornek: technical, liquidations, news, volumes, whales...)."""
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
async def deep_research(
    coin: str,
    timeframe: str = "1d",
    lookback_days: int = 365,
    platform: str = "generic",
    include_prompt: bool = False,
) -> dict[str, Any]:
    """66 maddelik arastirmayi calistirir; skor, olasilik, rapor ve prompt uretir."""
    settings, db, providers = _context()
    engine = DeepResearchEngine(providers, settings, db)
    try:
        output = await engine.run(
            coin,
            timeframe=timeframe,
            lookback_days=lookback_days,
            platform=platform,
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
    """Uretilmis raporlari listeler."""
    settings = get_settings()
    db = Database(settings.db_path)
    return db.list_reports(limit=limit)


@server.tool()
def get_report(name: str) -> dict[str, Any]:
    """Rapor adiyla markdown icerigini dondurur."""
    settings = get_settings()
    db = Database(settings.db_path)
    report = db.get_report(name)
    if not report:
        return {"error": "rapor bulunamadi"}
    return {"name": report["name"], "coin": report["coin"], "markdown": report["markdown"]}


@server.tool()
def get_run(run_id: str) -> dict[str, Any]:
    """Kosu detaylarini (66 madde sonuclari dahil) dondurur."""
    settings = get_settings()
    db = Database(settings.db_path)
    run = db.get_run(run_id)
    if not run:
        return {"error": "kosu bulunamadi"}
    return json.loads(run.model_dump_json())


def run_stdio() -> None:
    server.run("stdio")


def run_sse() -> None:
    server.run("sse")


if __name__ == "__main__":
    run_stdio()
