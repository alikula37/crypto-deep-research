"""FastAPI uygulaması: NotebookLM benzeri web UI'in backend'i."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from crypto_deep_research.analysis.base import AnalysisContext
from crypto_deep_research.analysis.engine import available_analyses, run_analyses
from crypto_deep_research.config import get_settings
from crypto_deep_research.deep_research.engine import DeepResearchEngine
from crypto_deep_research.deep_research.registry import registry_summary
from crypto_deep_research.llm import OpenRouterClient, OpenRouterError
from crypto_deep_research.providers.registry import build_providers
from crypto_deep_research.rag.engine import RAGEngine
from crypto_deep_research.storage.db import Database

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Crypto Deep Research",
    description="Kripto paralar için yerel RAG + 66 maddelik deep research sistemi",
    version="0.1.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AnalyzeRequest(BaseModel):
    coin: str
    analyses: list[str] | None = None
    timeframe: str = "1d"
    lookback_days: int = Field(default=365, ge=1, le=3650)


class DeepResearchRequest(AnalyzeRequest):
    platform: str = "generic"
    include_prompt: bool = True


class RagSearchRequest(BaseModel):
    query: str
    coin: str | None = None
    k: int = Field(default=8, ge=1, le=30)


class RagAskRequest(RagSearchRequest):
    model: str | None = None


class ReportRequest(BaseModel):
    prompt: str
    model: str | None = None


def _services() -> tuple[Any, Database, Any]:
    settings = get_settings()
    db = Database(settings.db_path)
    return settings, db, build_providers(settings, db)


@app.get("/api/health")
async def health() -> dict[str, Any]:
    settings = get_settings()
    db = Database(settings.db_path)
    return {
        "status": "ok",
        "openrouter": bool(settings.openrouter_api_key),
        "keys": {
            "coingecko": bool(settings.coingecko_api_key),
            "coinalyze": bool(settings.coinalyze_api_key),
            "cryptopanic": bool(settings.cryptopanic_api_key),
            "etherscan": bool(settings.etherscan_api_key),
            "fred": bool(settings.fred_api_key),
        },
        "reports": len(db.list_reports(limit=1000)),
    }


@app.get("/api/analyses")
async def analyses() -> list[dict[str, str]]:
    return available_analyses()


@app.get("/api/items")
async def items() -> list[dict[str, Any]]:
    return registry_summary()


@app.get("/api/snapshot/{coin}")
async def snapshot(coin: str) -> dict[str, Any]:
    settings, db, providers = _services()
    try:
        ref = await providers.coingecko.resolve(coin)
        data = await providers.coingecko.snapshot(ref)
        db.save_snapshot(ref.id, data.model_dump(mode="json"))
        global_market = await providers.coingecko.global_market()
        return {
            "snapshot": data.model_dump(mode="json"),
            "global": global_market.model_dump(mode="json"),
        }
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        await providers.aclose()


@app.post("/api/analyze")
async def analyze(request: AnalyzeRequest) -> dict[str, Any]:
    settings, db, providers = _services()
    try:
        ref = await providers.coingecko.resolve(request.coin)
        ctx = AnalysisContext(
            coin=ref,
            providers=providers,
            settings=settings,
            timeframe=request.timeframe,
            lookback_days=request.lookback_days,
        )
        results = await run_analyses(ctx, request.analyses)
        return {
            "coin": ref.model_dump(),
            "analyses": [result.model_dump(mode="json") for result in results],
        }
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        await providers.aclose()


@app.post("/api/deep-research")
async def deep_research(request: DeepResearchRequest) -> dict[str, Any]:
    settings, db, providers = _services()
    engine = DeepResearchEngine(providers, settings, db)
    try:
        output = await engine.run(
            request.coin,
            analyses=request.analyses,
            timeframe=request.timeframe,
            lookback_days=request.lookback_days,
            platform=request.platform,
        )
        return {
            "run": json.loads(output.run.model_dump_json()),
            "analyses": [result.model_dump(mode="json") for result in output.analysis_results],
            "report_path": output.report_path,
            "prompt_path": output.prompt_path,
            "prompt": output.prompt if request.include_prompt else None,
            "markdown": output.markdown,
            "context_stats": output.context_stats,
        }
    except Exception as exc:
        logger.exception("Deep research hatası")
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        await providers.aclose()


@app.post("/api/rag/search")
async def rag_search(request: RagSearchRequest) -> dict[str, Any]:
    settings = get_settings()
    db = Database(settings.db_path)
    engine = RAGEngine(db, settings)
    results = engine.search(request.query, coin=request.coin, k=request.k)
    return {"results": [result.model_dump(mode="json") for result in results]}


@app.post("/api/rag/ask")
async def rag_ask(request: RagAskRequest) -> dict[str, Any]:
    settings = get_settings()
    db = Database(settings.db_path)
    engine = RAGEngine(db, settings)
    prompt = engine.answer_prompt(request.query, coin=request.coin)
    client = OpenRouterClient(settings)
    if not client.enabled:
        return {"answer": None, "prompt": prompt, "note": "OpenRouter anahtari tanımli değil."}
    try:
        answer = await client.complete(prompt, model=request.model)
        return {"answer": answer, "prompt": prompt}
    except OpenRouterError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/reports")
async def reports() -> list[dict[str, Any]]:
    settings = get_settings()
    db = Database(settings.db_path)
    rows = db.list_reports(limit=200)
    known = {str(row["name"]) for row in rows}
    for path in settings.reports_dir.glob("*.md"):
        if path.stem in known:
            continue
        rows.append(
            {
                "name": path.stem,
                "run_id": None,
                "coin": path.stem.split("_")[0].lower(),
                "created_at": path.stat().st_mtime,
            }
        )
    rows.sort(key=lambda row: row.get("created_at") or 0, reverse=True)
    return rows[:200]


@app.get("/api/reports/{name}")
async def report(name: str) -> dict[str, Any]:
    settings = get_settings()
    db = Database(settings.db_path)
    data = db.get_report(name)
    if data:
        return data
    path = settings.reports_dir / f"{name}.md"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Rapor bulunamadı")
    return {
        "name": name,
        "run_id": None,
        "coin": name.split("_")[0].lower(),
        "created_at": path.stat().st_mtime,
        "markdown": path.read_text(encoding="utf-8"),
        "meta": None,
    }


@app.get("/api/runs")
async def runs(coin: str | None = None) -> list[dict[str, Any]]:
    settings = get_settings()
    db = Database(settings.db_path)
    return db.list_runs(coin=coin, limit=100)


@app.get("/api/runs/{run_id}")
async def run_detail(run_id: str) -> dict[str, Any]:
    settings = get_settings()
    db = Database(settings.db_path)
    run = db.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Kosu bulunamadı")
    return json.loads(run.model_dump_json())


@app.get("/api/contexts")
async def contexts(kind: str | None = None, coin: str | None = None) -> list[dict[str, Any]]:
    settings = get_settings()
    db = Database(settings.db_path)
    objects = db.list_contexts(kind=kind, scope_contains=coin, limit=300)
    return [obj.model_dump(mode="json") for obj in objects]


@app.get("/api/contexts/{key:path}")
async def context_detail(key: str) -> dict[str, Any]:
    settings = get_settings()
    db = Database(settings.db_path)
    obj = db.get_context(key)
    if not obj:
        raise HTTPException(status_code=404, detail="Context bulunamadı")
    return obj.model_dump(mode="json")


@app.get("/api/rag/stats")
async def rag_stats() -> dict[str, Any]:
    settings = get_settings()
    db = Database(settings.db_path)
    return RAGEngine(db, settings).stats()


# ------------------------------------------------------------------ statik web UI
def _mount_web() -> None:
    project_root = Path(__file__).resolve().parents[3]
    dist = project_root / "web" / "dist"
    if dist.exists():
        app.mount("/", StaticFiles(directory=str(dist), html=True), name="web")
        logger.info("Web UI sunuluyor: %s", dist)
    else:

        @app.get("/")
        async def index() -> JSONResponse:
            return JSONResponse(
                {
                    "message": "Web UI derlenmemis. 'cd web && npm install && npm run build' çalıştırin.",
                    "api_docs": "/docs",
                }
            )


_mount_web()
