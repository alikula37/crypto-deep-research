"""66 maddelik araştırma motoru: tüm analizleri, madde değerlendirmelerini ve skorlamayi yönetir."""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from crypto_deep_research.analysis.base import AnalysisContext, clamp
from crypto_deep_research.analysis.engine import DEFAULT_ANALYSES, run_analyses
from crypto_deep_research.config import Settings
from crypto_deep_research.context.control_plane import ContextControlPlane
from crypto_deep_research.deep_research.prompt_builder import build_prompt
from crypto_deep_research.deep_research.registry import ItemSpec, load_registry
from crypto_deep_research.deep_research.report import render_report
from crypto_deep_research.deep_research.specials import evaluate_item
from crypto_deep_research.models import (
    AnalysisResult,
    CoinRef,
    ItemResult,
    ResearchRun,
)
from crypto_deep_research.providers.registry import Providers
from crypto_deep_research.rag.engine import RAGEngine
from crypto_deep_research.storage.db import Database

logger = logging.getLogger(__name__)

ITEM_CONCURRENCY = 4


@dataclass
class DeepResearchOutput:
    run: ResearchRun
    prompt: str
    markdown: str
    analysis_results: list[AnalysisResult] = field(default_factory=list)
    report_path: str | None = None
    prompt_path: str | None = None
    context_stats: dict[str, Any] = field(default_factory=dict)


class DeepResearchEngine:
    def __init__(self, providers: Providers, settings: Settings, db: Database) -> None:
        self.providers = providers
        self.settings = settings
        self.db = db
        self.control_plane = ContextControlPlane(db, settings)
        self.rag = RAGEngine(db, settings)

    async def run(
        self,
        coin_query: str,
        *,
        analyses: list[str] | None = None,
        timeframe: str = "1d",
        lookback_days: int = 365,
        platform: str = "generic",
        include_all_items: bool = True,
    ) -> DeepResearchOutput:
        coin = await self.providers.coingecko.resolve(coin_query)
        ctx = AnalysisContext(
            coin=coin,
            providers=self.providers,
            settings=self.settings,
            timeframe=timeframe,
            lookback_days=lookback_days,
            platform=platform,
        )
        snapshot = await ctx.snapshot()
        selected = analyses or DEFAULT_ANALYSES
        analysis_results = await run_analyses(ctx, selected)
        analyses_map = {result.key: result for result in analysis_results}

        articles = await ctx.articles(hours=72)
        try:
            self.rag.ingest_articles(coin.id, articles)
            self.rag.ingest_analysis(coin.id, analysis_results)
        except Exception as exc:
            logger.warning("RAG indeksleme hatası: %s", exc)

        specs = load_registry()
        item_results = await self._evaluate_items(ctx, specs, analyses_map)
        if not include_all_items:
            item_results = [item for item in item_results if item.status in ("ok", "partial")]

        run = self._build_run(
            coin=coin,
            snapshot_price=snapshot.price_usd,
            analysis_results=analysis_results,
            item_results=item_results,
            timeframe=timeframe,
            lookback_days=lookback_days,
            platform=platform,
        )

        for analysis in analysis_results:
            self.control_plane.register_analysis(coin.id, analysis)
        for item in item_results:
            self.control_plane.register_item(coin.id, item)
        self.control_plane.register_run(run)
        self.db.save_run(run)

        prompt = build_prompt(run, analysis_results, item_results, self.control_plane)
        markdown = render_report(run, analysis_results, item_results, prompt=prompt)

        run_id = run.run_id
        safe_symbol = coin.symbol.upper()
        date_tag = run.created_at.strftime("%Y%m%d_%H%M")
        report_name = f"{safe_symbol}_{date_tag}_{run_id[:6]}"
        report_path = self.settings.reports_dir / f"{report_name}.md"
        prompt_path = self.settings.prompts_dir / f"{report_name}_prompt.txt"
        report_path.write_text(markdown, encoding="utf-8")
        prompt_path.write_text(prompt, encoding="utf-8")
        self.db.save_report(
            report_name,
            run_id,
            coin.id,
            markdown,
            {"prompt_path": str(prompt_path), "report_path": str(report_path)},
        )
        try:
            self.rag.ingest_report(coin.id, report_name, markdown)
        except Exception:
            logger.warning("Rapor RAG'e eklenemedi")

        contexts = self.db.list_contexts(scope_contains=coin.id, limit=500)
        _, context_stats = self.control_plane.materialize(contexts)

        return DeepResearchOutput(
            run=run,
            prompt=prompt,
            markdown=markdown,
            analysis_results=analysis_results,
            report_path=str(report_path),
            prompt_path=str(prompt_path),
            context_stats=context_stats,
        )

    async def _evaluate_items(
        self,
        ctx: AnalysisContext,
        specs: list[ItemSpec],
        analyses_map: dict[str, AnalysisResult],
    ) -> list[ItemResult]:
        semaphore = asyncio.Semaphore(ITEM_CONCURRENCY)
        results: dict[int, ItemResult] = {}

        async def _run(spec: ItemSpec) -> None:
            async with semaphore:
                results[spec.id] = await evaluate_item(ctx, spec, analyses_map)

        await asyncio.gather(*[_run(spec) for spec in specs])
        return [results[spec.id] for spec in specs if spec.id in results]

    @staticmethod
    def _build_run(
        *,
        coin: CoinRef,
        snapshot_price: float,
        analysis_results: list[AnalysisResult],
        item_results: list[ItemResult],
        timeframe: str,
        lookback_days: int,
        platform: str,
    ) -> ResearchRun:
        weighted_score = compute_weighted_score(item_results)
        up_probability, down_probability = probabilities(weighted_score)
        atr_pct = _atr_pct(analysis_results)
        expected_low, expected_high = expected_range(
            snapshot_price, atr_pct, weighted_score or 0.0
        )
        sources = _dedupe_sources(analysis_results, item_results)
        ok_items = sum(1 for item in item_results if item.status == "ok")
        partial_items = sum(1 for item in item_results if item.status == "partial")
        no_data_items = sum(1 for item in item_results if item.status in ("no_data", "error"))
        notes = [
            f"66 maddenin {ok_items} tanesi tam, {partial_items} tanesi kısmi veriyle değerlendirildi; "
            f"{no_data_items} madde için doğrulanabilir ücretsiz veri bulunamadı ve ortalamaya dahil edilmedi.",
            "Skorlar veri kaynaklarının ağırlıklı ortalamasıdır; kesin fiyat tahmini değildir.",
            "Yatırım tavsiyesi değildir.",
        ]
        return ResearchRun(
            run_id=uuid.uuid4().hex[:12],
            coin=coin,
            created_at=datetime.now(timezone.utc),
            timeframe=timeframe,
            lookback_days=lookback_days,
            platform=platform,
            analyses=[result.key for result in analysis_results],
            items=item_results,
            weighted_score=weighted_score,
            up_probability=up_probability,
            down_probability=down_probability,
            expected_low=expected_low,
            expected_high=expected_high,
            current_price=snapshot_price,
            sources=sources,
            notes=notes,
        )


def compute_weighted_score(items: list[ItemResult]) -> float | None:
    numerator = 0.0
    denominator = 0.0
    for item in items:
        if item.score is None or item.confidence <= 0:
            continue
        if item.status not in ("ok", "partial"):
            continue
        weight = item.weight * item.confidence
        numerator += item.score * weight
        denominator += weight
    if denominator == 0:
        return None
    return round(clamp(numerator / denominator), 4)


def probabilities(weighted_score: float | None) -> tuple[float, float]:
    if weighted_score is None:
        return 50.0, 50.0
    up = clamp(50 + 45 * weighted_score, 5.0, 95.0)
    return round(up, 1), round(100 - up, 1)


def _atr_pct(analysis_results: list[AnalysisResult]) -> float | None:
    for result in analysis_results:
        if result.key == "technical":
            value = ((result.data or {}).get("indicators") or {}).get("atr_pct")
            if value:
                return float(value)
    return None


def expected_range(
    price: float, atr_pct: float | None, weighted_score: float
) -> tuple[float, float]:
    base_move = max(atr_pct or 2.0, 1.0)
    horizon_factor = 1.0
    move_pct = base_move * horizon_factor * (1 + 0.4 * abs(weighted_score))
    skew = weighted_score * move_pct * 0.25
    low = price * (1 - move_pct / 100)
    high = price * (1 + move_pct / 100)
    if skew >= 0:
        high += price * skew / 100
    else:
        low += price * skew / 100
    return round(low, 8), round(high, 8)


def _dedupe_sources(
    analysis_results: list[AnalysisResult], item_results: list[ItemResult]
) -> list:
    seen: dict[str, Any] = {}
    for source in [s for result in analysis_results for s in result.sources] + [
        s for item in item_results for s in item.sources
    ]:
        key = source.name.lower()
        if key not in seen:
            seen[key] = source
    return list(seen.values())
