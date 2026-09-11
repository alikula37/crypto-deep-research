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
from crypto_deep_research.llm import OpenRouterClient
from crypto_deep_research.providers.registry import build_providers
from crypto_deep_research.rag.engine import RAGEngine
from crypto_deep_research.storage.db import Database

app = typer.Typer(
    name="cdr",
    help="Kripto Deep Research: yerel RAG, 66 maddelik arastirma ve MCP server.",
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
    """Anlik piyasa ozeti."""
    data = asyncio.run(_snapshot(coin))
    table = Table(title=f"{data['coin']['name']} ({data['coin']['symbol'].upper()})")
    table.add_column("Alan")
    table.add_column("Deger", justify="right")
    rows = [
        ("Fiyat", f"${data['price_usd']:,.6f}"),
        ("Piyasa degeri", f"${data.get('market_cap_usd') or 0:,.0f}"),
        ("Sira", str(data.get("rank"))),
        ("24s hacim", f"${data.get('volume_24h_usd') or 0:,.0f}"),
        ("24s degisim", f"%{data.get('change_24h_pct') or 0:.2f}"),
        ("7g degisim", f"%{data.get('change_7d_pct') or 0:.2f}"),
        ("30g degisim", f"%{data.get('change_30d_pct') or 0:.2f}"),
        ("ATH", f"${data.get('ath_usd') or 0:,.6f}"),
        ("ATH uzaklik", f"%{data.get('ath_change_pct') or 0:.2f}"),
        ("ATL", f"${data.get('atl_usd') or 0:,.6f}"),
        ("ATL uzaklik", f"%{data.get('atl_change_pct') or 0:.2f}"),
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
        None, "--types", "-t", help="Virgulle ayrilmis analizler: " + ", ".join(ANALYSIS_REGISTRY)
    ),
    timeframe: str = typer.Option("1d", "--timeframe", "-f"),
    days: int = typer.Option(365, "--days", "-d"),
    json_output: bool = typer.Option(False, "--json", help="Ham JSON cikti"),
):
    """Secili analizleri calistirir."""
    selected = [item.strip() for item in types.split(",")] if types else None
    results = asyncio.run(_analyze(coin, selected, timeframe, days))
    if json_output:
        console.print_json(json.dumps([result.model_dump(mode="json") for result in results]))
        return
    for result in results:
        score = f"{result.score:+.2f}" if result.score is not None else "n/a"
        color = "green" if (result.score or 0) > 0.15 else "red" if (result.score or 0) < -0.15 else "yellow"
        console.print(
            Panel(
                f"{result.summary}\n\nSkor: {score} | Guven: {result.confidence:.2f} | Durum: {result.status}",
                title=f"[bold]{result.title}[/bold]",
                border_style=color,
            )
        )


async def _deep_research(coin: str, types: list[str], timeframe: str, days: int, platform: str) -> dict:
    settings, db, providers = _providers()
    engine = DeepResearchEngine(providers, settings, db)
    try:
        output = await engine.run(
            coin,
            analyses=types,
            timeframe=timeframe,
            lookback_days=days,
            platform=platform,
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
    json_output: bool = typer.Option(False, "--json"),
):
    """66 maddelik deep research calistirir; rapor ve prompt uretir."""
    selected = [item.strip() for item in types.split(",")] if types else None
    result = asyncio.run(_deep_research(coin, selected, timeframe, days, platform))
    if json_output:
        console.print_json(json.dumps(result, default=str))
        return
    run = result["run"]
    console.print(
        Panel(
            f"Agirlikli skor: {run['weighted_score']}\n"
            f"Yukselis olasiligi: %{run['up_probability']} | Dusus: %{run['down_probability']}\n"
            f"Beklenen aralik: {run['expected_low']} - {run['expected_high']} USD",
            title="[bold]Deep Research Sonucu[/bold]",
            border_style="cyan",
        )
    )
    console.print(f"Rapor: [green]{result['report_path']}[/green]")
    console.print(f"Prompt: [green]{result['prompt_path']}[/green]")
    console.print(f"Context: {result['context_stats']}")


@app.command()
def items():
    """66 maddelik kayit defterini listeler."""
    table = Table(title="66 Maddelik Arastirma Listesi")
    table.add_column("#", justify="right")
    table.add_column("Madde")
    table.add_column("Kategori")
    table.add_column("Kaynak")
    table.add_column("Agirlik", justify="right")
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
    prompt: bool = typer.Option(False, "--prompt", help="LLM icin RAG prompt'u uret"),
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
        console.print("[yellow]Sonuc bulunamadi. Once deep-research calistirin.[/yellow]")
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
    """RAG baglamiyla OpenRouter uzerinden soru sorar (anahtar yoksa prompt yazdirir)."""
    settings = get_settings()
    db = Database(settings.db_path)
    rag = RAGEngine(db, settings)
    prompt = rag.answer_prompt(question, coin=coin)
    client = OpenRouterClient(settings)
    if not client.enabled:
        console.print("[yellow]OpenRouter anahtari yok; uretilen prompt:[/yellow]\n")
        console.print(prompt)
        return
    answer = asyncio.run(client.complete(prompt, model=model))
    console.print(Panel(answer, title="OpenRouter yaniti", border_style="cyan"))


@app.command()
def mcp():
    """MCP server'i stdio uzerinden calistirir."""
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
    """HTTP onbellegini yonetir."""
    settings = get_settings()
    db = Database(settings.db_path)
    if clear:
        count = db.cache_clear(provider)
        console.print(f"[green]{count} onbellek kaydi silindi.[/green]")
        return
    table = Table(title="Onbellek Istatistikleri")
    table.add_column("Saglayici")
    table.add_column("Kayit", justify="right")
    table.add_column("Son guncelleme")
    for row in db.cache_stats():
        table.add_row(
            row["provider"],
            str(row["entries"]),
            str(__import__("datetime").datetime.fromtimestamp(row["last_at"]).strftime("%Y-%m-%d %H:%M")),
        )
    console.print(table)


@app.command("rag-stats")
def rag_stats():
    """RAG deposunun durumunu gosterir."""
    settings = get_settings()
    db = Database(settings.db_path)
    engine = RAGEngine(db, settings)
    console.print_json(json.dumps(engine.stats(), ensure_ascii=False, default=str))


@app.command("analyses")
def analyses_command():
    """Kullanilabilir analiz anahtarlarini listeler."""
    for item in available_analyses():
        console.print(f"- [bold]{item['key']}[/bold]: {item['title']}")


if __name__ == "__main__":
    app()
