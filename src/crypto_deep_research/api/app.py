"""FastAPI uygulaması: NotebookLM benzeri web UI'in backend'i."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from crypto_deep_research.analysis.base import AnalysisContext
from crypto_deep_research.analysis.engine import available_analyses, run_analyses
from crypto_deep_research.api.jobs import Job, JobManager
from crypto_deep_research.config import get_settings
from crypto_deep_research.deep_research.accuracy import compute_accuracy
from crypto_deep_research.deep_research.engine import DeepResearchEngine, DeepResearchOutput
from crypto_deep_research.deep_research.profiles import profile_summary
from crypto_deep_research.deep_research.registry import registry_summary
from crypto_deep_research.llm import OpenRouterClient, OpenRouterError
from crypto_deep_research.models import Kline
from crypto_deep_research.portfolio import value_portfolio
from crypto_deep_research.providers.registry import build_providers
from crypto_deep_research.rag.engine import RAGEngine
from crypto_deep_research.storage.db import Database

logger = logging.getLogger(__name__)


def _due_watchlist(entries: list[dict[str, Any]], now: float, interval_hours: float) -> list[dict[str, Any]]:
    """Otomatik kosusu zamani gelmis takip kayitlarini secer."""
    return [
        entry
        for entry in entries
        if entry.get("auto_run") and now - (entry.get("last_run_at") or 0) >= interval_hours * 3600
    ]


async def _watchlist_scheduler() -> None:
    """Takip listesindeki coinler icin periyodik derin arastirma baslatir."""
    settings = get_settings()
    interval = max(60, settings.watchlist_interval_minutes * 60)
    while True:
        await asyncio.sleep(interval)
        if not settings.watchlist_enabled or jobs.has_running():
            continue
        try:
            db = Database(settings.db_path)
            due = _due_watchlist(
                db.watchlist_list(), time.time(), settings.watchlist_auto_run_hours
            )
        except Exception:
            logger.exception("Takip listesi okunamadi")
            continue
        for entry in due:
            try:
                db.watchlist_touch(entry["coin"])
                job = jobs.create(
                    _make_deep_runner(
                        DeepResearchRequest(
                            coin=entry["coin"],
                            timeframe=entry.get("timeframe") or "1d",
                            profile=entry.get("profile") or "balanced",
                            include_prompt=True,
                        )
                    )
                )
                logger.info("Otomatik takip koşusu başlatıldı: %s (%s)", entry["coin"], job.id)
            except Exception:
                logger.exception("Otomatik koşu başlatılamadı: %s", entry["coin"])
            break  # ayni anda tek kosu


@asynccontextmanager
async def lifespan(_: FastAPI):
    task = asyncio.create_task(_watchlist_scheduler())
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


app = FastAPI(
    title="Crypto Deep Research",
    description="Kripto paralar için yerel RAG + 66 maddelik deep research sistemi",
    version="0.2.0",
    lifespan=lifespan,
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
    profile: str = "balanced"
    language: str = "tr"
    include_prompt: bool = True


class WatchlistRequest(BaseModel):
    coin: str
    symbol: str | None = None
    name: str | None = None
    profile: str = "balanced"
    timeframe: str = "1d"
    auto_run: bool = True


class WatchlistUpdateRequest(BaseModel):
    profile: str | None = None
    timeframe: str | None = None
    auto_run: bool | None = None


class TranslateRequest(BaseModel):
    language: str = "en"


class PortfolioRequest(BaseModel):
    coin: str
    amount: float = Field(gt=0)
    entry_price: float = Field(gt=0)
    note: str | None = None


class PortfolioUpdateRequest(BaseModel):
    amount: float | None = Field(default=None, gt=0)
    entry_price: float | None = Field(default=None, gt=0)
    note: str | None = None


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


def _serialize_output(output: DeepResearchOutput, include_prompt: bool) -> dict[str, Any]:
    return {
        "run": json.loads(output.run.model_dump_json()),
        "analyses": [result.model_dump(mode="json") for result in output.analysis_results],
        "report_path": output.report_path,
        "prompt_path": output.prompt_path,
        "prompt": output.prompt if include_prompt else None,
        "markdown": output.markdown,
        "context_stats": output.context_stats,
    }


jobs = JobManager()


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


@app.get("/api/profiles")
async def profiles() -> list[dict[str, str]]:
    return profile_summary()


@app.get("/api/items")
async def items() -> list[dict[str, Any]]:
    return registry_summary()


@app.get("/api/coins/search")
async def search_coins(q: str = "", limit: int = 10) -> dict[str, Any]:
    """Varlik arama (otomatik tamamlama); CoinGecko /search, yedek yerel liste."""
    settings, db, providers = _services()
    try:
        results = await providers.coingecko.search(q, limit=min(max(limit, 1), 25))
        return {"query": q, "results": results}
    finally:
        await providers.aclose()


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
            profile=request.profile,
        )
        return _serialize_output(output, request.include_prompt)
    except Exception as exc:
        logger.exception("Derin araştırma hatası")
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        await providers.aclose()


def _make_deep_runner(request: DeepResearchRequest):
    async def runner(job: Job) -> dict[str, Any]:
        settings, db, providers = _services()
        engine = DeepResearchEngine(providers, settings, db)
        job.update(1, "Veri kaynakları hazırlanıyor…")
        try:
            output = await engine.run(
                request.coin,
                analyses=request.analyses,
                timeframe=request.timeframe,
                lookback_days=request.lookback_days,
                platform=request.platform,
                profile=request.profile,
                language=request.language,
                progress=job.update,
            )
            return _serialize_output(output, request.include_prompt)
        finally:
            await providers.aclose()

    return runner


@app.post("/api/deep-research/jobs")
async def start_deep_research_job(request: DeepResearchRequest) -> dict[str, Any]:
    """Uzun süren derin araştırmayı arka planda başlatır; ilerleme sorgulanabilir."""
    jobs.prune()
    job = jobs.create(_make_deep_runner(request))
    return {"job_id": job.id, "status": job.status, "message": job.message}


@app.get("/api/deep-research/jobs/{job_id}")
async def deep_research_job_status(job_id: str) -> dict[str, Any]:
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Görev bulunamadı")
    return job.to_dict()


@app.get("/api/watchlist")
async def watchlist() -> list[dict[str, Any]]:
    settings = get_settings()
    db = Database(settings.db_path)
    return db.watchlist_list()


@app.post("/api/watchlist")
async def watchlist_add(request: WatchlistRequest) -> dict[str, Any]:
    settings, db, providers = _services()
    try:
        ref = await providers.coingecko.resolve(request.coin)
        db.watchlist_add(
            ref.id,
            symbol=request.symbol or ref.symbol.upper(),
            name=request.name or ref.name,
            profile=request.profile,
            timeframe=request.timeframe,
            auto_run=request.auto_run,
        )
        return db.watchlist_get(ref.id) or {}
    finally:
        await providers.aclose()


@app.patch("/api/watchlist/{coin}")
async def watchlist_update(coin: str, request: WatchlistUpdateRequest) -> dict[str, Any]:
    settings = get_settings()
    db = Database(settings.db_path)
    entry = db.watchlist_get(coin)
    if not entry:
        raise HTTPException(status_code=404, detail="Takip listesinde bulunamadı")
    db.watchlist_add(
        coin,
        symbol=entry.get("symbol"),
        name=entry.get("name"),
        profile=request.profile or entry["profile"],
        timeframe=request.timeframe or entry["timeframe"],
        auto_run=entry["auto_run"] if request.auto_run is None else request.auto_run,
    )
    return db.watchlist_get(coin) or {}


@app.delete("/api/watchlist/{coin}")
async def watchlist_remove(coin: str) -> dict[str, Any]:
    settings = get_settings()
    db = Database(settings.db_path)
    db.watchlist_remove(coin)
    return {"removed": coin}


@app.get("/api/portfolio")
async def portfolio() -> dict[str, Any]:
    """Portfoy pozisyonlarini guncel fiyatlarla degerler."""
    settings, db, providers = _services()
    try:
        return await value_portfolio(providers, db)
    finally:
        await providers.aclose()


@app.post("/api/portfolio")
async def portfolio_add(request: PortfolioRequest) -> dict[str, Any]:
    settings, db, providers = _services()
    try:
        ref = await providers.coingecko.resolve(request.coin)
        position_id = db.portfolio_add(
            ref.id,
            symbol=ref.symbol.upper(),
            name=ref.name,
            amount=request.amount,
            entry_price=request.entry_price,
            note=request.note,
        )
        return db.portfolio_get(position_id) or {}
    finally:
        await providers.aclose()


@app.patch("/api/portfolio/{position_id}")
async def portfolio_update(position_id: int, request: PortfolioUpdateRequest) -> dict[str, Any]:
    settings = get_settings()
    db = Database(settings.db_path)
    if not db.portfolio_get(position_id):
        raise HTTPException(status_code=404, detail="Pozisyon bulunamadı")
    db.portfolio_update(
        position_id, amount=request.amount, entry_price=request.entry_price, note=request.note
    )
    return db.portfolio_get(position_id) or {}


@app.delete("/api/portfolio/{position_id}")
async def portfolio_remove(position_id: int) -> dict[str, Any]:
    settings = get_settings()
    db = Database(settings.db_path)
    db.portfolio_remove(position_id)
    return {"removed": position_id}


@app.post("/api/watchlist/{coin}/run")
async def watchlist_run(coin: str) -> dict[str, Any]:
    """Takip listesindeki coin icin hemen derin arastirma baslatir."""
    settings = get_settings()
    db = Database(settings.db_path)
    entry = db.watchlist_get(coin)
    if not entry:
        raise HTTPException(status_code=404, detail="Takip listesinde bulunamadı")
    if jobs.has_running():
        raise HTTPException(status_code=409, detail="Zaten çalışan bir araştırma var; bitince deneyin.")
    jobs.prune()
    job = jobs.create(
        _make_deep_runner(
            DeepResearchRequest(
                coin=coin,
                timeframe=entry.get("timeframe") or "1d",
                profile=entry.get("profile") or "balanced",
                include_prompt=True,
            )
        )
    )
    return {"job_id": job.id, "status": job.status, "message": job.message}


@app.get("/api/ohlcv/{coin}")
async def ohlcv(coin: str, timeframe: str = "1d", limit: int = 300) -> dict[str, Any]:
    """Timeframe bazli mum verisi (Binance, yedek CoinGecko)."""
    settings, db, providers = _services()
    try:
        ref = await providers.coingecko.resolve(coin)
        klines: list[Kline] = await providers.exchange.klines(
            ref.symbol, timeframe, min(max(limit, 30), 1000)
        )
        source_name = "Binance"
        if not klines:
            days_map = {"15m": 1, "30m": 1, "1h": 7, "4h": 14, "1d": 90, "1w": 365}
            days = days_map.get(timeframe, 90)
            chart = await providers.coingecko.market_chart(ref.id, days=days)
            prices = [pair for pair in chart.get("prices") or [] if pair and pair[1]]
            klines = [
                Kline(
                    ts=__import__("datetime").datetime.fromtimestamp(
                        pair[0] / 1000, tz=__import__("datetime").timezone.utc
                    ),
                    open=float(pair[1]),
                    high=float(pair[1]),
                    low=float(pair[1]),
                    close=float(pair[1]),
                    volume=0.0,
                )
                for pair in prices[-min(max(limit, 30), 1000) :]
            ]
            source_name = "CoinGecko (kapanis fiyatlari)"
        return {
            "coin": ref.model_dump(),
            "timeframe": timeframe,
            "source": source_name,
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
    except Exception as exc:
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


@app.post("/api/reports/{name}/translate")
async def translate_report(name: str, request: TranslateRequest) -> dict[str, Any]:
    """Raporu OpenRouter ile hedef dile cevirir (CDR_OPENROUTER_API_KEY gerekir)."""
    settings = get_settings()
    db = Database(settings.db_path)
    data = db.get_report(name)
    if not data:
        path = settings.reports_dir / f"{name}.md"
        if not path.exists():
            raise HTTPException(status_code=404, detail="Rapor bulunamadı")
        data = {"markdown": path.read_text(encoding="utf-8")}
    client = OpenRouterClient(settings)
    if not client.enabled:
        raise HTTPException(
            status_code=400,
            detail="Çeviri için CDR_OPENROUTER_API_KEY tanımlı olmalıdır.",
        )
    target = "İngilizce" if request.language.lower().startswith("en") else request.language
    prompt = (
        f"Aşağıdaki Markdown raporunu {target} diline çevir. Markdown yapısını, başlıkları, "
        "tabloları, sayı biçimlerini ve tüm rakamları aynen koru; hiçbir bölümü özetleme, "
        "çıkarma veya yorum ekleme; yalnızca çevrilmiş Markdown metnini döndür.\n\n"
        + (data.get("markdown") or "")
    )
    try:
        translated = await client.complete(
            prompt,
            system=(
                "Sen profesyonel bir finansal çevirmensin. Kaynak metnin yapısını bozmadan, "
                "terimleri doğru karşılıklarıyla çevirirsin."
            ),
            max_tokens=8000,
            temperature=0.2,
        )
    except OpenRouterError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"name": name, "language": request.language, "markdown": translated}


@app.get("/api/runs")
async def runs(coin: str | None = None) -> list[dict[str, Any]]:
    settings = get_settings()
    db = Database(settings.db_path)
    return db.run_summaries(coin=coin, limit=100)


@app.get("/api/runs/{run_id}")
async def run_detail(run_id: str) -> dict[str, Any]:
    settings = get_settings()
    db = Database(settings.db_path)
    run = db.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Kosu bulunamadı")
    return json.loads(run.model_dump_json())


@app.get("/api/accuracy")
async def accuracy(coin: str | None = None) -> dict[str, Any]:
    """Gecmis kosularin skorlarini sonraki fiyat getirileriyle karsilastirir."""
    settings, db, providers = _services()
    try:
        return await compute_accuracy(providers, db, coin=coin)
    finally:
        await providers.aclose()


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
