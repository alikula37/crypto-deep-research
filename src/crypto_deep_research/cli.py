"""Komut satiri arayuzu (cdr)."""

from __future__ import annotations

import asyncio
import json

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
from crypto_deep_research.rag.engine import RAGEngine
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
    for index, result in enumerate(results, 1):
        when = result.timestamp.strftime("%Y-%m-%d %H:%M") if result.timestamp else "?"
        console.print(f"[bold]{index}. {result.source or '?'}[/bold] ({when}) skor={result.score:.3f}")
        console.print(f"   {result.content[:300]}")


@app.command()
def ask(
    question: str = typer.Argument(...),
    coin: str | None = typer.Option(None, "--coin", "-c"),
    model: str | None = typer.Option(None, "--model"),
):
    """RAG bağlamıyla OpenRouter üzerinden soru sorar (anahtar yoksa prompt yazdırir)."""
    settings = get_settings()
    db = Database(settings.db_path)
    rag = RAGEngine(db, settings)
    prompt = rag.answer_prompt(question, coin=coin)
    client = OpenRouterClient(settings)
    if not client.enabled:
        console.print("[yellow]OpenRouter anahtari yok; üretilen prompt:[/yellow]\n")
        console.print(prompt)
        return
    answer = asyncio.run(client.complete(prompt, model=model))
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
            str(__import__("datetime").datetime.fromtimestamp(row["last_at"]).strftime("%Y-%m-%d %H:%M")),
        )
    console.print(table)


@app.command("rag-stats")
def rag_stats():
    """RAG deposunun durumunu gösterir."""
    settings = get_settings()
    db = Database(settings.db_path)
    engine = RAGEngine(db, settings)
    console.print_json(json.dumps(engine.stats(), ensure_ascii=False, default=str))


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
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Ozniteliklerden yon modeli egitir (purged walk-forward + Platt kalibrasyon)."""
    from crypto_deep_research.learning.trainer import train_all, train_horizon

    settings = get_settings()
    db = Database(settings.db_path)
    results = (
        [train_horizon(db, horizon, min_samples=min_samples)]
        if horizon
        else train_all(db, min_samples=min_samples)
    )
    if json_output:
        console.print_json(json.dumps(results, default=str))
        return
    for result in results:
        if result["status"] == "insufficient":
            console.print(
                f"  {result['horizon_days']}g: yetersiz örnek ({result['n']}/{result['min_samples']})"
            )
            continue
        metrics = result.get("metrics", {})
        console.print(
            f"  {result['horizon_days']}g: {result['model_status']} · n={result['n']} · "
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
            f"  {model['model_id']} · {model['status']} · n={model['train_rows']} · {model['metrics']}"
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
