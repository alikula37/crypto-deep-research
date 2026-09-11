"""Markdown rapor uretimi (Turkce)."""

from __future__ import annotations

import json
from datetime import timezone

from crypto_deep_research.models import AnalysisResult, ItemResult, ResearchRun

STATUS_LABELS = {
    "ok": "Tam",
    "partial": "Kismi",
    "no_data": "Veri yok",
    "error": "Hata",
}


def render_report(
    run: ResearchRun,
    analyses: list[AnalysisResult],
    items: list[ItemResult],
    prompt: str | None = None,
) -> str:
    now = run.created_at.astimezone(timezone.utc)
    price = run.current_price or 0.0
    lines: list[str] = [
        f"# {run.coin.name} ({run.coin.symbol.upper()}) - Kripto Deep Research Raporu",
        "",
        f"- **Tarih:** {now.strftime('%d.%m.%Y %H:%M UTC')}",
        f"- **Fiyat:** ${price:,.6f}".rstrip("0").rstrip("."),
        f"- **Timeframe:** {run.timeframe} | **Gecmis penceresi:** {run.lookback_days} gun",
        f"- **Agirlikli skor:** {run.weighted_score}",
        f"- **Yukselis / Dusus olasiligi:** %{run.up_probability} / %{run.down_probability}",
        f"- **Beklenen aralik:** {run.expected_low} - {run.expected_high} USD",
        "",
        "> Bu rapor otomatik uretilmistir ve yatirim tavsiyesi degildir. Skorlar veri agirlikli",
        "> tahminlerdir; kesinlik iddiası tasimaz.",
        "",
        "## 10 Ana Analiz",
        "",
        "| Analiz | Durum | Skor | Guven | Ozet |",
        "| --- | --- | --- | --- | --- |",
    ]
    for analysis in analyses:
        summary = (analysis.summary or "").replace("|", "/").replace("\n", " ")[:160]
        score = f"{analysis.score:+.2f}" if analysis.score is not None else "-"
        lines.append(
            f"| {analysis.title} | {STATUS_LABELS.get(analysis.status, analysis.status)} | "
            f"{score} | {analysis.confidence:.2f} | {summary} |"
        )
    lines.append("")

    for analysis in analyses:
        lines.append(f"### {analysis.title}")
        lines.append("")
        lines.append(analysis.summary or "_Ozet yok_")
        lines.append("")
        reasons = (analysis.data or {}).get("reasons")
        if reasons:
            lines.append("**Nedenler:**")
            for reason in reasons[:10]:
                lines.append(f"- {reason}")
            lines.append("")
        if analysis.sources:
            lines.append(
                "**Kaynaklar:** " + ", ".join(sorted({s.name for s in analysis.sources}))
            )
            lines.append("")

    lines.extend(
        [
            "## 66 Maddelik Arastirma Tablosu",
            "",
            "| # | Madde | Durum | Skor | Guven | Ozet |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for item in items:
        summary = (item.summary or "").replace("|", "/").replace("\n", " ")[:120]
        score = f"{item.score:+.2f}" if item.score is not None else "-"
        lines.append(
            f"| {item.item_id} | {item.title_tr} | {STATUS_LABELS.get(item.status, item.status)} | "
            f"{score} | {item.confidence:.2f} | {summary} |"
        )
    lines.append("")

    lines.append("## Madde Detaylari")
    lines.append("")
    for item in items:
        lines.append(f"### {item.item_id}. {item.title_tr}")
        lines.append("")
        lines.append(f"- **Durum:** {STATUS_LABELS.get(item.status, item.status)}")
        lines.append(
            f"- **Skor / Guven:** {item.score if item.score is not None else '-'} / {item.confidence:.2f}"
        )
        lines.append(f"- **Ozet:** {item.summary or '-'}")
        reasons = (item.data or {}).get("reasons")
        if reasons:
            lines.append("- **Nedenler:** " + "; ".join(str(reason) for reason in reasons[:6]))
        if item.sources:
            lines.append(
                "- **Kaynaklar:** " + ", ".join(sorted({s.name for s in item.sources}))
            )
        if item.warnings:
            lines.append("- **Uyarilar:** " + "; ".join(item.warnings))
        lines.append("")

    lines.extend(["## Kullanilan Kaynaklar", ""])
    for source in sorted({s.name for s in run.sources}):
        lines.append(f"- {source}")
    lines.append("")

    if prompt:
        lines.extend(["## Prompt Dosyasi", "", "Harici AI'a verilecek prompt ayni isimli `_prompt.txt` dosyasindadir.", ""])

    lines.extend(
        [
            "## Metodoloji ve Sinirlamalar",
            "",
            "- Veriler ucretsiz API katmanlarindan toplanir (CoinGecko, Binance, Coinalyze, DefiLlama,",
            "  CryptoPanic, RSS, GDELT, alternative.me, Reddit, Google Trends, Blockchain.com,",
            "  mempool.space, Blockchair, Blockscout, Etherscan, yfinance, FRED, Deribit).",
            "- Her madde veri + kaynak + guven ile raporlanir; verisi olmayan maddeler ortalamaya",
            "  dahil edilmez ve raporda acikca isaretlenir.",
            "- Skorlar -1 (guclu negatif) ile +1 (guclu pozitif) arasindadir; agirlikli ortalama",
            "  guven katsayisi ile hesaplanir.",
            f"- Politika ozeti (Context Control Plane): {json.dumps(run.notes, ensure_ascii=False)}",
            "",
        ]
    )
    return "\n".join(lines)
