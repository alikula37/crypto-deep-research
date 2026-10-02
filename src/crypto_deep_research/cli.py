"""Komut satiri arayuzu (cdr)."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from crypto_deep_research.analysis.base import AnalysisContext
from crypto_deep_research.analysis.engine import ANALYSIS_REGISTRY, available_analyses, run_analyses
from crypto_deep_research.config import get_settings
from crypto_deep_research.deep_research.engine import DeepResearchEngine
from crypto_deep_research.deep_research.registry import registry_summary
from crypto_deep_research.formatting import (
    money,
    pct,
)
from crypto_deep_research.formatting import (
    price as fmt_price,
)
from crypto_deep_research.formatting import (
    score as fmt_score,
)
from crypto_deep_research.llm import OpenRouterClient
from crypto_deep_research.providers.registry import build_providers
from crypto_deep_research.rag.answer_evaluation import evaluate_answers, load_answer_cases
from crypto_deep_research.rag.engine import RAGEngine
from crypto_deep_research.rag.evaluation import evaluate_retrieval, load_cases
from crypto_deep_research.storage.db import Database

app = typer.Typer(
    name="cdr",
    help="Kripto Deep Research: yerel RAG, 66 maddelik araştırma ve MCP server.",
    no_args_is_help=True,
)
console = Console()


def _providers():
    settings = get_settings()
    db = Database(settings.db_path)
    return settings, db, build_providers(settings, db)


async def _snapshot(coin: str) -> dict:
    settings, db, providers = _providers()
    try:
        ref = await providers.coingecko.resolve(coin)
        snapshot = await providers.coingecko.snapshot(ref)
        db.save_snapshot(ref.id, snapshot.model_dump(mode="json"))
        return snapshot.model_dump(mode="json")
    finally:
        await providers.aclose()


@app.command()
def snapshot(coin: str = typer.Argument(..., help="Coin sembolu veya id (btc, bitcoin...)")):
    """Anlık piyasa özeti."""
    data = asyncio.run(_snapshot(coin))
    table = Table(title=f"{data['coin']['name']} ({data['coin']['symbol'].upper()})")
    table.add_column("Alan")
    table.add_column("Değer", justify="right")
    rows = [
        ("Fiyat", fmt_price(data["price_usd"])),
        ("Piyasa değeri", money(data.get("market_cap_usd"))),
        ("Sıra", str(data.get("rank") or "-")),
        ("24s hacim", money(data.get("volume_24h_usd"))),
        ("24s değişim", pct(data.get("change_24h_pct"), signed=True)),
        ("7g değişim", pct(data.get("change_7d_pct"), signed=True)),
        ("30g değişim", pct(data.get("change_30d_pct"), signed=True)),
        ("ATH", fmt_price(data.get("ath_usd"))),
        ("ATH uzaklık", pct(data.get("ath_change_pct"))),
        ("ATL", fmt_price(data.get("atl_usd"))),
        ("ATL uzaklık", pct(data.get("atl_change_pct"))),
    ]
    for label, value in rows:
        table.add_row(label, value)
    console.print(table)


async def _analyze(coin: str, types: list[str], timeframe: str, days: int) -> list:
    settings, db, providers = _providers()
    try:
        ref = await providers.coingecko.resolve(coin)
        ctx = AnalysisContext(
            coin=ref,
            providers=providers,
            settings=settings,
            timeframe=timeframe,
            lookback_days=days,
        )
        return await run_analyses(ctx, types)
    finally:
        await providers.aclose()


@app.command()
def analyze(
    coin: str = typer.Argument(...),
    types: str | None = typer.Option(
        None, "--types", "-t", help="Virgulle ayrılmis analizler: " + ", ".join(ANALYSIS_REGISTRY)
    ),
    timeframe: str = typer.Option("1d", "--timeframe", "-f"),
    days: int = typer.Option(365, "--days", "-d"),
    json_output: bool = typer.Option(False, "--json", help="Ham JSON çıktı"),
):
    """Seçili analizleri çalıştırir."""
    selected = [item.strip() for item in types.split(",")] if types else None
    results = asyncio.run(_analyze(coin, selected, timeframe, days))
    if json_output:
        console.print_json(json.dumps([result.model_dump(mode="json") for result in results]))
        return
    for result in results:
        score = fmt_score(result.score)
        color = "green" if (result.score or 0) > 0.15 else "red" if (result.score or 0) < -0.15 else "yellow"
        status_label = {
            "ok": "Tam",
            "partial": "Kısmi",
            "no_data": "Veri yok",
            "error": "Hata",
        }.get(result.status, result.status)
        console.print(
            Panel(
                f"{result.summary}\n\nSkor: {score} | Güven: {result.confidence:.2f} | "
                f"Durum: {status_label}",
                title=f"[bold]{result.title}[/bold]",
                border_style=color,
            )
        )


async def _deep_research(
    coin: str,
    types: list[str],
    timeframe: str,
    days: int,
    platform: str,
    profile: str = "balanced",
    language: str = "tr",
) -> dict:
    settings, db, providers = _providers()
    engine = DeepResearchEngine(providers, settings, db)
    try:
        output = await engine.run(
            coin,
            analyses=types,
            timeframe=timeframe,
            lookback_days=days,
            platform=platform,
            profile=profile,
            language=language,
        )
        return {
            "run": output.run.model_dump(mode="json"),
            "prompt_path": output.prompt_path,
            "report_path": output.report_path,
            "context_stats": output.context_stats,
        }
    finally:
        await providers.aclose()


@app.command("deep-research")
def deep_research(
    coin: str = typer.Argument(...),
    types: str | None = typer.Option(None, "--types", "-t"),
    timeframe: str = typer.Option("1d", "--timeframe", "-f"),
    days: int = typer.Option(365, "--days", "-d"),
    platform: str = typer.Option("generic", "--platform", help="generic|claude|codex|chatgpt"),
    profile: str = typer.Option(
        "balanced", "--profile", help="balanced|conservative|aggressive skorlama profili"
    ),
    language: str = typer.Option("tr", "--lang", help="Prompt dili: tr|en"),
    json_output: bool = typer.Option(False, "--json"),
):
    """66 maddelik deep research çalıştırir; rapor ve prompt üretir."""
    selected = [item.strip() for item in types.split(",")] if types else None
    result = asyncio.run(_deep_research(coin, selected, timeframe, days, platform, profile, language))
    if json_output:
        console.print_json(json.dumps(result, default=str))
        return
    run = result["run"]
    console.print(
        Panel(
            f"Ağırlıklı skor: {run['weighted_score']}\n"
            f"Yükseliş olasılığı: %{run['up_probability']} | Düşüş: %{run['down_probability']}\n"
            f"Beklenen aralık: {run['expected_low']} - {run['expected_high']} USD",
            title="[bold]Deep Research Sonuçu[/bold]",
            border_style="cyan",
        )
    )
    console.print(f"Rapor: [green]{result['report_path']}[/green]")
    console.print(f"Prompt: [green]{result['prompt_path']}[/green]")
    console.print(f"Context: {result['context_stats']}")


@app.command()
def items():
    """66 maddelik kayıt defterini listeler."""
    table = Table(title="Araştırma Kriterleri (66)")
    table.add_column("#", justify="right")
    table.add_column("Madde")
    table.add_column("Kategori")
    table.add_column("Kaynak")
    table.add_column("Ağırlık", justify="right")
    for item in registry_summary():
        table.add_row(
            str(item["id"]), item["title"], item["category"], item["source"], f"{item['weight']:.2f}"
        )
    console.print(table)


@app.command()
def search(
    query: str = typer.Argument(...),
    coin: str | None = typer.Option(None, "--coin", "-c"),
    k: int = typer.Option(8, "--k"),
    prompt: bool = typer.Option(False, "--prompt", help="LLM için RAG prompt'u üret"),
    json_output: bool = typer.Option(False, "--json", help="Kaynak kimlikleriyle JSON çıktı"),
):
    """Yerel RAG deposunda arama yapar."""
    settings = get_settings()
    db = Database(settings.db_path)
    engine = RAGEngine(db, settings)
    if prompt:
        console.print(engine.answer_prompt(query, coin=coin))
        return
    results = engine.search(query, coin=coin, k=k)
    if not results:
        console.print("[yellow]Sonuç bulunamadı. Once deep-research çalıştırin.[/yellow]")
        return
    if json_output:
        console.print_json(
            json.dumps(
                [
                    {
                        "id": result.key,
                        "parent_id": result.parent_id or result.key,
                        "chunk_index": result.chunk_index,
                        "score": result.score,
                        "score_type": result.score_type,
                        "source": result.source,
                        "url": result.url,
                        "coin": result.coin,
                        "kind": result.kind,
                        "content": result.content,
                    }
                    for result in results
                ],
                ensure_ascii=False,
            )
        )
        return
    for index, result in enumerate(results, 1):
        when = result.timestamp.strftime("%Y-%m-%d %H:%M") if result.timestamp else "?"
        console.print(f"[bold]{index}. {result.source or '?'}[/bold] ({when}) skor={result.score:.3f}")
        console.print(f"   {result.content[:300]}")


@app.command("rag-eval")
def rag_eval(
    dataset: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True),
    ks: str = typer.Option("1,3,5,10", "--ks", help="Virgülle ayrılmış Recall/Precision cut-off'ları"),
    split: str = typer.Option("all", "--split", help="Değerlendirme kümesi: all, dev veya test"),
    retrieval_mode: str = typer.Option(
        "hybrid", "--retrieval", help="Karşılaştırma modu: hybrid, dense veya bm25"
    ),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Etiketli JSONL sorgularıyla hibrit RAG retrieval kalitesini ölçer."""
    try:
        cutoffs = [int(value.strip()) for value in ks.split(",") if value.strip()]
        if not cutoffs or any(k < 1 for k in cutoffs):
            raise ValueError("--ks pozitif tamsayılardan oluşmalı")
        if retrieval_mode not in {"hybrid", "dense", "bm25"}:
            raise ValueError("--retrieval hybrid, dense veya bm25 olmalı")
        cases = load_cases(dataset, split=split)
    except (ValueError, OSError) as exc:
        raise typer.BadParameter(str(exc)) from exc

    settings = get_settings()
    db = Database(settings.db_path)
    engine = RAGEngine(db, settings)
    result = evaluate_retrieval(
        lambda query, coin, k: engine.search(
            query, coin=coin, k=k, mode=retrieval_mode
        ),
        cases,
        ks=cutoffs,
    )
    output = {
        **result,
        "split": split,
        "configured_chunking": {
            "strategy": settings.rag_chunk_strategy,
            "chunk_tokens": settings.rag_chunk_tokens,
            "overlap_tokens": settings.rag_chunk_overlap_tokens,
        },
        "retrieval": {
            "mode": retrieval_mode,
            "fusion": "reciprocal_rank_fusion" if retrieval_mode == "hybrid" else None,
            "dense_enabled": settings.embeddings_enabled,
            "reranker_model": settings.rag_reranker_model,
        },
    }
    if json_output:
        console.print_json(json.dumps(output, ensure_ascii=False))
        return

    table = Table(title=f"RAG Retrieval Evaluation · {result['n_queries']} sorgu")
    table.add_column("k", justify="right")
    for metric in ("precision", "recall", "hit_rate", "mrr", "ndcg"):
        table.add_column(metric)
    for k, metrics in result["metrics"].items():
        values = (f"{metrics[name]:.3f}" for name in ("precision", "recall", "hit_rate", "mrr", "ndcg"))
        table.add_row(str(k), *values)
    console.print(table)
    console.print(
        f"Mod: {retrieval_mode} · dense={'açık' if settings.embeddings_enabled else 'kapalı'} · "
        f"reranker={settings.rag_reranker_model or 'kapalı'} · split={split} · etiketler: {dataset}"
    )


@app.command("rag-answer-eval")
def rag_answer_eval(
    dataset: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True),
    split: str = typer.Option("all", "--split", help="Değerlendirme kümesi: all, dev veya test"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """İnsan etiketleriyle RAG cevaplarının dayanağını ve atıflarını ölçer."""
    try:
        cases = load_answer_cases(dataset, split=split)
        result = evaluate_answers(cases)
    except (ValueError, OSError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    output = {**result, "split": split}
    if json_output:
        console.print_json(json.dumps(output, ensure_ascii=False))
        return

    table = Table(title=f"RAG Answer Evaluation · {result['n_answers']} yanıt · {split}")
    table.add_column("Metrik")
    table.add_column("Cevap makro", justify="right")
    table.add_column("İddia/atıf mikro", justify="right")
    macro = result["metrics"]["macro_by_answer"]
    micro = result["metrics"]["micro_by_claim_or_citation"]
    for name in ("faithfulness", "citation_coverage", "citation_precision"):
        macro_value = macro[name]
        micro_value = micro[name]
        table.add_row(
            name,
            f"{macro_value:.3f}" if macro_value is not None else "n/a",
            f"{micro_value:.3f}" if micro_value is not None else "n/a",
        )
    table.add_row(
        "answer_relevance (1–5)",
        f"{macro['answer_relevance']:.2f}",
        "—",
    )
    console.print(table)
    console.print(f"Etiketler: {dataset} · iddialar={result['n_claims']} · atıflar={result['n_citations']}")


@app.command()
def ask(
    question: str = typer.Argument(...),
    coin: str | None = typer.Option(None, "--coin", "-c"),
    model: str | None = typer.Option(None, "--model"),
    json_output: bool = typer.Option(False, "--json", help="Yanıtı ve kaynakları etiketleme için yazdır"),
):
    """RAG bağlamıyla OpenRouter üzerinden soru sorar (anahtar yoksa prompt yazdırir)."""
    settings = get_settings()
    db = Database(settings.db_path)
    rag = RAGEngine(db, settings)
    results = rag.search(question, coin=coin)
    prompt = rag.answer_prompt(question, coin=coin, results=results)
    client = OpenRouterClient(settings)
    answer = None
    if not client.enabled:
        if not json_output:
            console.print("[yellow]OpenRouter anahtari yok; üretilen prompt:[/yellow]\n")
            console.print(prompt)
    else:
        answer = asyncio.run(client.complete(prompt, model=model))

    if json_output:
        source_rows = [
            {
                "citation_index": index,
                "parent_id": item.parent_id or item.key.partition("#chunk-")[0],
                "source": item.source,
                "url": item.url,
                "content": item.content,
                "score": item.score,
                "score_type": item.score_type,
            }
            for index, item in enumerate(results, 1)
        ]
        parent_ids = list(dict.fromkeys(row["parent_id"] for row in source_rows))
        console.print_json(
            json.dumps(
                {
                    "query": question,
                    "answer": answer,
                    "model": model or (settings.openrouter_model if client.enabled else None),
                    "prompt": prompt,
                    "retrieval": {
                        "mode": "hybrid",
                        "reranker_model": settings.rag_reranker_model,
                    },
                    "retrieved_parent_ids": parent_ids,
                    "retrieved_sources": source_rows,
                },
                ensure_ascii=False,
            )
        )
    elif answer is not None:
        console.print(Panel(answer, title="OpenRouter yaniti", border_style="cyan"))


@app.command()
def mcp():
    """MCP server'i stdio üzerinden çalıştırir."""
    from crypto_deep_research.mcp_server import run_stdio

    run_stdio()


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8000, "--port"),
    reload: bool = typer.Option(False, "--reload"),
):
    """Web UI + REST API sunar."""
    import uvicorn

    uvicorn.run(
        "crypto_deep_research.api.app:app",
        host=host,
        port=port,
        reload=reload,
    )


@app.command("cache")
def cache_command(
    stats: bool = typer.Option(False, "--stats"),
    clear: bool = typer.Option(False, "--clear"),
    provider: str | None = typer.Option(None, "--provider"),
):
    """HTTP onbellegini yönetir."""
    settings = get_settings()
    db = Database(settings.db_path)
    if clear:
        count = db.cache_clear(provider)
        console.print(f"[green]{count} önbellek kaydi silindi.[/green]")
        return
    table = Table(title="Önbellek İstatistikleri")
    table.add_column("Sağlayıcı")
    table.add_column("Kayıt", justify="right")
    table.add_column("Son güncelleme")
    for row in db.cache_stats():
        table.add_row(
            row["provider"],
            str(row["entries"]),
            str(datetime.fromtimestamp(row["last_at"]).strftime("%Y-%m-%d %H:%M")),
        )
    console.print(table)


@app.command("rag-stats")
def rag_stats():
    """RAG deposunun durumunu gösterir."""
    settings = get_settings()
    db = Database(settings.db_path)
    engine = RAGEngine(db, settings)
    console.print_json(json.dumps(engine.stats(), ensure_ascii=False, default=str))


@app.command("rag-reindex")
def rag_reindex(
    chunk_tokens: int | None = typer.Option(None, "--chunk-tokens", min=1),
    overlap_tokens: int | None = typer.Option(None, "--overlap-tokens", min=0),
    strategy: str | None = typer.Option(None, "--strategy", help="sentence (cümle sınırları) veya token (sabit pencere). Bu indeksleme için geçerli."),
) -> None:
    """Tam kaynak metinlerden RAG indeksini yeni chunk ayarlarıyla oluşturur."""
    settings = get_settings()
    db = Database(settings.db_path)
    engine = RAGEngine(db, settings)
    try:
        result = engine.reindex(chunk_tokens=chunk_tokens, overlap_tokens=overlap_tokens, strategy=strategy)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    effective_chunk = chunk_tokens or settings.rag_chunk_tokens
    effective_overlap = (
        settings.rag_chunk_overlap_tokens if overlap_tokens is None else overlap_tokens
    )
    console.print_json(
        json.dumps(
            {
                **result,
                "chunk_tokens": effective_chunk,
                "overlap_tokens": effective_overlap,
                "strategy": settings.rag_chunk_strategy if strategy is None else strategy,
            },
            ensure_ascii=False,
        )
    )


@app.command("analyses")
def analyses_command():
    """Kullanılabilir analiz anahtarlarini listeler."""
    for item in available_analyses():
        console.print(f"- [bold]{item['key']}[/bold]: {item['title']}")


@app.command("learning-backfill")
def learning_backfill(
    limit: int = typer.Option(500, "--limit", help="Islenecek maksimum kosu sayisi"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Mevcut kosulardan ogrenme ozelliklerini geriye donuk cikarir."""
    from crypto_deep_research.deep_research.engine import compute_group_factors
    from crypto_deep_research.deep_research.profiles import weight_multipliers
    from crypto_deep_research.deep_research.registry import load_registry
    from crypto_deep_research.learning.features import persist_run
    from crypto_deep_research.models import ResearchRun

    settings = get_settings()
    db = Database(settings.db_path)
    specs = load_registry()
    factors = compute_group_factors(specs)
    rows = db.runs_missing_features(limit=limit)
    written = 0
    for row in rows:
        try:
            run = ResearchRun.model_validate_json(row["payload"])
        except Exception:
            continue
        multipliers = weight_multipliers(getattr(run, "profile", "balanced"), specs)
        if persist_run(db, run, specs, group_factors=factors, multipliers=multipliers):
            written += 1
    payload = {"missing": len(rows), "written": written}
    if json_output:
        console.print_json(json.dumps(payload))
        return
    console.print(f"{written} koşu için özellikler yazıldı ({len(rows)} eksikti).")


@app.command("learning-fill")
def learning_fill() -> None:
    """Vadesi gelen ileri getiri etiketlerini hemen doldurur."""
    from crypto_deep_research.learning.outcomes import fill_due_outcomes

    settings, db, providers = _providers()

    async def _run() -> dict:
        try:
            return await fill_due_outcomes(
                providers, db, max_attempts=settings.outcome_max_attempts
            )
        finally:
            await providers.aclose()

    result = asyncio.run(_run())
    console.print(
        f"Vadesi gelen: {result['due']} · doldurulan: {result['filled']} · "
        f"bekleyen: {result['pending']} · eksik: {result['missing']}"
    )


@app.command("ml-train")
def ml_train(
    horizon: int = typer.Option(0, "--horizon", help="0: tum ufuklar (1/7/30)"),
    min_samples: int = typer.Option(30, "--min-samples", help="Egitim icin gereken asgari etiket"),
    source: str = typer.Option("live", "--source", help="live | backfill | all"),
    features: str = typer.Option(
        "base",
        "--features",
        help="base (varsayilan) | base+extended | all",
    ),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Yon modeli egitir; model secimi, kalibrasyon ve final holdout donemlerini ayirir."""
    from crypto_deep_research.learning.trainer import train_all, train_horizon

    settings = get_settings()
    db = Database(settings.db_path)
    resolved_source = None if source == "all" else source
    group_map = {
        "base": ["base"],
        "base+extended": ["base", "extended"],
        "base+extended+cross": ["base", "extended", "cross"],
        "all": ["base", "extended", "cross"],
    }
    feature_groups = group_map.get(features, None)
    from crypto_deep_research.learning.cross_section import compute_cross_section

    for target in (("live", "backfill") if resolved_source is None else (resolved_source,)):
        info = compute_cross_section(db, source=target)
        if info.get("written") and not json_output:
            console.print(
                f"  kesitsel [{target}]: {info['written']} özellik güncellendi "
                f"({info.get('coins', 0)} coin, {info.get('days', 0)} gün)"
            )
    results = (
        [
            train_horizon(
                db, horizon, min_samples=min_samples, source=resolved_source,
                feature_groups=feature_groups,
            )
        ]
        if horizon
        else train_all(
            db, min_samples=min_samples, source=resolved_source, feature_groups=feature_groups
        )
    )
    if json_output:
        console.print_json(json.dumps(results, default=str))
        return
    for result in results:
        if result["status"] != "trained":
            details = [f"n={result.get('n', 0)}"]
            if "n_calibration" in result:
                details.append(
                    f"cal={result['n_calibration']}/{result.get('min_calibration', '?')}"
                )
            if "n_holdout" in result:
                details.append(f"holdout={result['n_holdout']}/{result.get('min_holdout', '?')}")
            console.print(
                f"  {result['horizon_days']}g [{result.get('source', source)}]: "
                f"{result['status']} · {' · '.join(details)}"
            )
            continue
        metrics = result.get("metrics", {})
        console.print(
            f"  {result['horizon_days']}g [{result.get('source', 'live')}]: {result['model_status']} · n={result['n']} · "
            f"AUC {metrics.get('auc')} · Brier {metrics.get('brier')} "
            f"(temel {metrics.get('baseline_brier')}) · ECE {metrics.get('ece')}"
        )


@app.command("ml-eval")
def ml_eval(
    horizon: int = typer.Option(7, "--horizon"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Kayitli modellerin durumunu ve metriklerini gosterir."""
    settings = get_settings()
    db = Database(settings.db_path)
    models = [model for model in db.model_list() if model["horizon_days"] == horizon]
    if json_output:
        console.print_json(json.dumps(models, default=str))
        return
    if not models:
        console.print(f"{horizon}g için kayıtlı model yok.")
        return
    for model in models:
        console.print(
            f"  {model['model_id']} · {model['status']} · n={model['train_rows']} · "
            f"protocol={model.get('evaluation_protocol') or 'legacy'} · {model['metrics']}"
        )


@app.command("ml-activate")
def ml_activate(
    model_id: str = typer.Argument(...),
    retire_others: bool = typer.Option(True, "--retire-others/--keep-others"),
) -> None:
    """Bir modeli aktiflestirir; ayni ufuktaki digerlerini emekliye ayirir."""
    settings = get_settings()
    db = Database(settings.db_path)
    target = next((model for model in db.model_list() if model["model_id"] == model_id), None)
    if target is None:
        console.print(f"[red]Model bulunamadı: {model_id}[/red]")
        raise typer.Exit(code=1)
    if retire_others:
        for model in db.model_list():
            if model["model_id"] != model_id and model["horizon_days"] == target["horizon_days"]:
                db.model_set_status(model["model_id"], "retired")
    db.model_set_status(model_id, "active")
    console.print(f"{model_id} aktifleştirildi (ufuk {target['horizon_days']}g).")


@app.command("ml-retire")
def ml_retire(model_id: str = typer.Argument(...)) -> None:
    """Bir modeli emekliye ayirir."""
    settings = get_settings()
    db = Database(settings.db_path)
    db.model_set_status(model_id, "retired")
    console.print(f"{model_id} emekliye ayrıldı.")


@app.command("learning-drift")
def learning_drift(
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Kapsam, skor dagilimi ve kalibrasyon icin drift metriklerini hesaplar."""
    from crypto_deep_research.learning.drift import compute_drift, drift_summary

    settings = get_settings()
    db = Database(settings.db_path)
    entries = compute_drift(
        db, window_days=settings.drift_window_days, baseline_days=settings.drift_baseline_days
    )
    summary = drift_summary(entries)
    if json_output:
        console.print_json(json.dumps(summary, default=str))
        return
    if not entries:
        console.print("Drift icin yeterli veri yok.")
        return
    for entry in entries:
        flag = "ALARM" if entry.get("alarm") else "ok"
        console.print(
            f"  {entry['metric']}: {flag} · deger {entry.get('value')} · temel {entry.get('baseline')}"
            + (f" · PSI {entry.get('psi')}" if entry.get("psi") is not None else "")
        )


@app.command("archive")
def archive_command(
    days: int = typer.Option(0, "--days", help="0: ayardaki CDR_ARCHIVE_RUNS_DAYS degeri"),
    path: str = typer.Option("data/archive/runs.sqlite", "--path"),
    delete: bool = typer.Option(False, "--delete", help="Arsive kopyaladiktan sonra ana DB'den sil"),
) -> None:
    """Eski kosulari ve raporlari ayri bir SQLite dosyasina arsivler."""
    from crypto_deep_research.storage.archive import archive_runs

    settings = get_settings()
    db = Database(settings.db_path)
    result = archive_runs(
        db,
        archive_path=path,
        older_than_days=days or settings.archive_runs_days,
        delete=delete,
    )
    console.print(
        f"{result['runs']} koşu, {result['reports']} rapor arşivlendi → {result['path']}"
        + (f" · silinen kayıt: {result['deleted']}" if delete else " (silme kapalı)")
    )


@app.command("strategy-scan")
def strategy_scan(
    days: int = typer.Option(900, "--days", help="Test edilecek gun sayisi"),
    cost_bps: float = typer.Option(6.0, "--cost-bps", help="Islem basi maliyet (bps)"),
    top: int = typer.Option(12, "--top", help="Gosterilecek en iyi satir sayisi"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Kanitli strateji ailelerini (TSMOM/XSMOM/CARRY/BREAK) ayni maliyetle tarar."""
    from crypto_deep_research.learning.strategies import load_daily, scan

    settings, db, providers = _providers()
    universe = Database.DEFAULT_WATCHLIST

    async def _run() -> list[dict]:
        try:
            frames = {}
            funding: dict[str, dict[str, float]] = {}
            for coin, symbol, _name in universe:
                frame = await load_daily(providers, symbol, days)
                if len(frame) > 150:
                    frames[coin] = frame
                rows = await providers.exchange.funding_history(symbol, days=days)
                daily: dict[str, list[float]] = {}
                for timestamp, rate in rows:
                    day = datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc).date().isoformat()
                    daily.setdefault(day, []).append(rate)
                if daily:
                    funding[coin] = {day: sum(values) for day, values in daily.items()}
            return scan(frames, funding, cost_bps=cost_bps)
        finally:
            await providers.aclose()

    results = [row for row in asyncio.run(_run()) if row.get("sharpe") is not None]
    results.sort(key=lambda row: -row["sharpe"])
    if json_output:
        console.print_json(json.dumps(results, default=str))
        return
    console.print(f"{len(results)} sonuc · maliyet {cost_bps} bps · {days} gun")
    table = Table("Aile", "Parametre", "Yillik", "Sharpe", "MaxDD", "BTC kor")
    for row in results[:top]:
        table.add_row(
            row["family"], row["params"],
            f"%{row['annual_return']*100:.1f}" if row.get("annual_return") is not None else "—",
            f"{row['sharpe']:.2f}", f"%{row['max_drawdown']*100:.1f}",
            f"{row['corr_btc']:.2f}" if row.get("corr_btc") is not None else "—",
        )
    console.print(table)


@app.command("carry-paper")
def carry_paper(
    step: bool = typer.Option(False, "--step", help="Bugunun paper adimini calistir"),
    ranking: bool = typer.Option(False, "--ranking", help="Canli fonlama siralamasini goster"),
    reset: bool = typer.Option(False, "--reset", help="Paper durumunu sifirla"),
    universe: int = typer.Option(40, "--universe", help="Taranacak likit perp sayisi"),
    top_n: int = typer.Option(8, "--top-n", help="Tutulacak coin sayisi"),
) -> None:
    """Carry stratejisi paper takibi (gunluk fonlama toplama simulasyonu)."""
    from crypto_deep_research.learning.carry import (
        fetch_funding_map,
        next_rebalance_date,
        paper_step,
        rank_funding,
        status,
    )

    settings, db, providers = _providers()

    async def _run() -> None:
        try:
            if reset:
                db.carry_state_clear()
                console.print("Paper durumu sifirlandi.")
                return
            if ranking:
                symbols = await providers.exchange.perp_universe(top=universe)
                funding = await fetch_funding_map(providers, symbols, days=30)
                ranked = rank_funding(funding, top_n=top_n, lookback=7)
                table = Table("Coin", "7g ort. fonlama (gunluk)", "Gun", "Secili")
                for row in ranked[:20]:
                    table.add_row(
                        row["symbol"], f"%{row['avg_funding']*100:.4f}", str(row["days"]),
                        "✓" if row["selected"] else "",
                    )
                console.print(table)
                return
            if step:
                result = await paper_step(db, providers, {"universe": universe, "top_n": top_n})
                state = result.get("state")
                if result["status"] != "ok" or not state:
                    console.print(f"Adim calistirilamadi: {result.get('status')} {result.get('reason', '')}")
                    return
                console.print(
                    f"Paper adim: {state['as_of']} · equity {state['equity']:.4f} · "
                    f"gunluk %{state['daily_return']*100:.4f}"
                    + (" · YENIDEN DENGELENDI" if state.get("rebalanced") else "")
                )
                for holding in state["holdings"]:
                    console.print(
                        f"  {holding['symbol']:12s} agirlik %{holding['weight']*100:5.2f} · "
                        f"7g fonlama %{(holding.get('avg_funding') or 0)*100:.4f}"
                    )
                return
            snapshot = status(db)
            state = snapshot.get("state")
            if not state:
                console.print("Paper takip henuz baslamadi: cdr carry-paper --step")
                return
            console.print(
                f"Equity {state['equity']:.4f} · gunluk %{state['daily_return']*100:.4f} · "
                f"sonraki rebalance {next_rebalance_date(state)} · {state.get('note') or ''}"
            )
            for holding in state["holdings"]:
                console.print(
                    f"  {holding['symbol']:12s} agirlik %{holding['weight']*100:5.2f}"
                )
        finally:
            await providers.aclose()

    asyncio.run(_run())


@app.command("carry-lab")
def carry_lab(
    days: int = typer.Option(2000, "--days", help="Fonlama gecmisi gunu"),
    cost_bps: float = typer.Option(6.0, "--cost-bps"),
    universe: int = typer.Option(0, "--universe", help="0=mevcut 10 coin; >0: en likit N perp"),
    top_n: int = typer.Option(4, "--top-n", help="Kesitsel secimde tutulacak coin sayisi"),
    pit: bool = typer.Option(False, "--pit", help="Nokta-zamaninda evren (survivorship kontrolu)"),
) -> None:
    """Fonlama carry varyantlarini uzun vadede karsilastirir."""
    from crypto_deep_research.learning.strategies import (
        build_pit_funding,
        carry_frame,
        carry_xs,
        metrics,
    )

    settings, db, providers = _providers()

    async def _load() -> dict[str, dict[str, float]]:
        try:
            if pit:
                masked, coverage = await build_pit_funding(
                    providers, days=days, top=40, candidates=60
                )
                console.print(f"PIT evren maske kapsami: %{coverage*100:.1f}")
                return masked
            if universe > 0:
                pairs = await providers.exchange.perp_universe(top=universe)
            else:
                pairs = [symbol for _coin, symbol, _name in Database.DEFAULT_WATCHLIST]
            funding: dict[str, dict[str, float]] = {}
            for symbol in pairs:
                rows = await providers.exchange.funding_history(symbol, days=days)
                daily: dict[str, list[float]] = {}
                for timestamp, rate in rows:
                    day = datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc).date().isoformat()
                    daily.setdefault(day, []).append(rate)
                if daily:
                    funding[symbol] = {day: sum(values) for day, values in daily.items()}
            return funding
        finally:
            await providers.aclose()

    funding = asyncio.run(_load())
    if not funding:
        console.print("Fonlama verisi alinamadi.")
        raise typer.Exit(code=1)
    frame = carry_frame(funding)
    start, end = frame.index.min(), frame.index.max()

    variants = {
        f"esit agir ({len(funding)} coin)": _equal_carry(funding, cost_bps),
        f"kesitsel ust-{top_n} (filtresiz)": carry_xs(funding, top_n=top_n, rebalance=7, cost_bps=cost_bps, target_vol=None, min_avg=-1.0),
        f"kesitsel ust-{top_n} + filtre": carry_xs(funding, top_n=top_n, rebalance=7, cost_bps=cost_bps, target_vol=None, min_avg=0.0),
        f"kesitsel ust-{top_n} + tavan %0.5": carry_xs(funding, top_n=top_n, rebalance=7, cost_bps=cost_bps, target_vol=None, min_avg=0.0, max_avg=0.005),
        "nihai (3g + hyst 2bp)": carry_xs(funding, top_n=top_n, rebalance=3, cost_bps=cost_bps, target_vol=None, min_avg=0.0, max_avg=0.005, hysteresis=0.0002),
        f"kesitsel ust-{top_n} + vol %10": carry_xs(funding, top_n=top_n, rebalance=7, cost_bps=cost_bps, target_vol=0.10, max_leverage=3.0),
    }
    console.print(f"Fonlama carry laboratuvari · {len(funding)} coin · {start.date()} → {end.date()}")
    table = Table("Varyant", "Yillik", "Sharpe", "MaxDD", "Vol", "Gun")
    for name, series in variants.items():
        stats = metrics(series.tolist() if hasattr(series, "tolist") else series)
        if not stats.get("sharpe"):
            continue
        table.add_row(
            name, f"%{stats['annual_return']*100:.1f}", f"{stats['sharpe']:.2f}",
            f"%{stats['max_drawdown']*100:.1f}", f"%{stats['vol_annual']*100:.1f}",
            str(stats["days"]),
        )
    console.print(table)


def _equal_carry(funding: dict[str, dict[str, float]], cost_bps: float):
    from crypto_deep_research.learning.strategies import _portfolio, carry_series

    return _portfolio({coin: carry_series(series, cost_bps=cost_bps) for coin, series in funding.items()})


@app.command("ml-portfolio")
def ml_portfolio(
    horizon: int = typer.Option(30, "--horizon", help="OOS tahmin ufku (1/7/30)"),
    top_k: int = typer.Option(3, "--top-k", help="Secilecek en iyi coin sayisi"),
    cost_bps: float = typer.Option(10.0, "--cost-bps", help="Islem basi maliyet (bps)"),
    rebalance_days: int = typer.Option(30, "--rebalance-days"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """OOS model siralamasiyla kesitsel portfoy backtest'i (ust-k vs evren vs BTC)."""
    from crypto_deep_research.learning.portfolio import run_backtest

    settings = get_settings()
    db = Database(settings.db_path)
    result = run_backtest(
        db, horizon=horizon, top_k=top_k, cost_bps=cost_bps, rebalance_days=rebalance_days
    )
    if json_output:
        console.print_json(json.dumps(result, default=str))
        return
    if result.get("status") != "ok":
        console.print(f"Backtest calistirilamadi: {result.get('reason', 'bilinmeyen')}")
        return
    equity = result["equity"]
    sharpe = result["net_sharpe"]
    console.print(
        f"{result['periods']} donem · {result['rebalance_days']}g yeniden dengeleme · maliyet {cost_bps} bps"
    )
    console.print(
        f"  Ust-{top_k}: {equity['top_k']:.2f}x (net Sharpe {sharpe['top_k']}) · "
        f"Long-short: {equity['long_short']:.2f}x ({sharpe['long_short']})"
    )
    console.print(
        f"  Esit agirlik: {equity['equal_weight']:.2f}x ({sharpe['equal_weight']}) · "
        f"BTC: {equity['btc']:.2f}x ({sharpe['btc']})"
    )
    console.print(
        f"  Ort. ust-k getirisi %{result['avg_top_k_return_pct']} · "
        f"ust-alt fark %{result['avg_spread_pct']} · isabet %{result['hit_rate']*100:.0f}"
    )


@app.command("ml-cross-section")
def ml_cross_section(
    source: str = typer.Option("backfill", "--source", help="backfill | live"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Ayni gun icin coinlerin birbirine gore konumunu (kesitsel ozellikler) hesaplar."""
    from crypto_deep_research.learning.cross_section import compute_cross_section

    settings = get_settings()
    db = Database(settings.db_path)
    result = compute_cross_section(db, source=source)
    if json_output:
        console.print_json(json.dumps(result, default=str))
        return
    if result.get("written"):
        console.print(
            f"{result['written']} kesitsel özellik yazıldı ({result['coins']} coin, {result['days']} gün, {source})."
        )
    else:
        console.print(f"Kesitsel özellik üretilemedi: {result.get('reason', 'bilinmeyen')}")


@app.command("ml-backfill-history")
def ml_backfill_history(
    coin: str = typer.Option("bitcoin", "--coin"),
    days: int = typer.Option(730, "--days", help="Replay edilecek gun sayisi"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Fiyat turevli maddeleri gecmis gunler icin yeniden hesaplayip egitim seti uretir."""
    from crypto_deep_research.learning.replay import replay_coin

    settings, db, providers = _providers()

    async def _run() -> dict:
        try:
            ref = await providers.coingecko.resolve(coin)
            return await replay_coin(providers, db, ref.id, ref.symbol.upper(), days=days)
        finally:
            await providers.aclose()

    result = asyncio.run(_run())
    if json_output:
        console.print_json(json.dumps(result, default=str))
        return
    if result.get("samples"):
        console.print(
            f"{result['coin']}: {result['samples']} tarihsel ornek yazildi "
            f"({result.get('history_days', 0)} gunluk seri, backfill_v1)."
        )
    else:
        console.print(f"{result['coin']}: ornek uretilemedi ({result.get('reason', 'bilinmeyen')}).")


@app.command("telegram")
def telegram_command(
    token: str | None = typer.Option(
        None, "--token", help="Telegram bot tokeni (yoksa CDR_TELEGRAM_TOKEN kullanilir)"
    ),
) -> None:
    """Telegram botunu baslatir: /fiyat, /skor, /rapor, /arastir komutlari."""
    from crypto_deep_research.telegram_bot import run_bot

    try:
        asyncio.run(run_bot(token))
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    except KeyboardInterrupt:
        console.print("Bot durduruldu.")


@app.command("prompt")
def prompt_command(
    coin: str = typer.Argument(..., help="Coin kimligi veya sembolu (orn. bitcoin)"),
    raw: bool = typer.Option(False, "--raw", help="Yalnizca prompt metnini yazdir (pipe icin)"),
) -> None:
    """Coin icin en son uretilen promptu yazdirir (Claude Code/Codex pipe entegrasyonu)."""
    from crypto_deep_research.prompt_store import latest_prompt

    settings = get_settings()
    db = Database(settings.db_path)
    data = latest_prompt(db, settings, coin)
    if not data:
        console.print(f"[red]{coin} için kayıtlı prompt bulunamadı.[/red]")
        raise typer.Exit(code=1)
    if raw:
        print(data["prompt"])
        return
    console.print(f"[bold]{data['name']}[/bold] ({data['path']})")
    console.print(data["prompt"])


if __name__ == "__main__":
    app()
