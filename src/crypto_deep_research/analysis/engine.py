"""Analiz motoru: seçili analizleri paralel çalıştırir."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from crypto_deep_research.analysis.ath_atl import analyze_ath_atl
from crypto_deep_research.analysis.base import AnalysisContext
from crypto_deep_research.analysis.liquidations import analyze_liquidations
from crypto_deep_research.analysis.marketcap import analyze_marketcap
from crypto_deep_research.analysis.news_analysis import analyze_news
from crypto_deep_research.analysis.parity import analyze_parity
from crypto_deep_research.analysis.rankings import analyze_rankings
from crypto_deep_research.analysis.revenue import analyze_revenue
from crypto_deep_research.analysis.technical import analyze_technical
from crypto_deep_research.analysis.volumes import analyze_volumes
from crypto_deep_research.analysis.whales import analyze_whales
from crypto_deep_research.models import AnalysisResult

logger = logging.getLogger(__name__)

AnalysisFn = Callable[[AnalysisContext], Awaitable[AnalysisResult]]

ANALYSIS_REGISTRY: dict[str, tuple[str, AnalysisFn]] = {
    "technical": ("Teknik Analiz", analyze_technical),
    "liquidations": ("Likidasyon Haritası ve Türev Piyasalar", analyze_liquidations),
    "whales": ("Balina Alım-Satım / Toplam Arz", analyze_whales),
    "volumes": ("Tüm Borsalardaki Hacimler", analyze_volumes),
    "revenue": ("Gelirler, Fee'ler ve Mcap Oranı", analyze_revenue),
    "news": ("Son Haberler ve Sentiment", analyze_news),
    "marketcap": ("Geçmiş Mcap / Güncel Mcap", analyze_marketcap),
    "parity": ("BTC/ETH Paritesi ve Direnç", analyze_parity),
    "ath_atl": ("USD ATH/ATL Mesafesi", analyze_ath_atl),
    "rankings": ("Mcap Sıralaması", analyze_rankings),
}

DEFAULT_ANALYSES: list[str] = list(ANALYSIS_REGISTRY.keys())


def available_analyses() -> list[dict[str, str]]:
    return [{"key": key, "title": title} for key, (title, _) in ANALYSIS_REGISTRY.items()]


async def run_analyses(
    ctx: AnalysisContext, keys: list[str] | None = None
) -> list[AnalysisResult]:
    selected = [key for key in (keys or DEFAULT_ANALYSES) if key in ANALYSIS_REGISTRY]
    if not selected:
        selected = DEFAULT_ANALYSES
    tasks = [ANALYSIS_REGISTRY[key][1](ctx) for key in selected]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    output: list[AnalysisResult] = []
    for key, result in zip(selected, results, strict=False):
        title = ANALYSIS_REGISTRY[key][0]
        if isinstance(result, Exception):
            logger.exception("Analiz hatası (%s)", key)
            output.append(
                ctx.result(
                    key,
                    title,
                    status="error",
                    summary=f"Analiz çalıştırılamadı: {result}",
                    score=None,
                    confidence=0.0,
                )
            )
        else:
            output.append(result)
    return output
