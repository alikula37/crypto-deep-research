"""Markdown rapor uretimi (Turkce, tr-TR sayi bicimi)."""

from __future__ import annotations

from datetime import timezone

from crypto_deep_research.formatting import price, price_range, score, truncate
from crypto_deep_research.models import AnalysisResult, ItemResult, ResearchRun

STATUS_LABELS = {
    "ok": "Tam",
    "partial": "Kısmi",
    "no_data": "Veri yok",
    "error": "Hata",
}

TABLE_SUMMARY_LIMIT = 220


def _summary_cell(text: str | None, limit: int = TABLE_SUMMARY_LIMIT) -> str:
    cleaned = (text or "").replace("|", "/").replace("\n", " ").strip()
    return truncate(cleaned, limit)


def render_report(
    run: ResearchRun,
    analyses: list[AnalysisResult],
    items: list[ItemResult],
    prompt: str | None = None,
) -> str:
    created = run.created_at.astimezone(timezone.utc)
    ok_count = sum(1 for item in items if item.status == "ok")
    partial_count = sum(1 for item in items if item.status == "partial")
    missing_count = sum(1 for item in items if item.status in ("no_data", "error"))
    scored = [item for item in items if item.score is not None and item.confidence > 0]

    lines: list[str] = [
        f"# {run.coin.name} ({run.coin.symbol.upper()}) - Kripto Deep Research Raporu",
        "",
        f"- **Tarih:** {created.strftime('%d.%m.%Y %H:%M')} UTC",
        f"- **Fiyat:** {price(run.current_price)}",
        f"- **Timeframe:** {run.timeframe} | **Geçmiş penceresi:** {run.lookback_days} gün",
        f"- **Ağırlıklı skor:** {score(run.weighted_score)}",
        f"- **Yükseliş / Düşüş olasılığı:** %{run.up_probability:.1f} / %{run.down_probability:.1f}",
        f"- **Beklenen aralık:** {price_range(run.expected_low, run.expected_high)}",
        f"- **66 madde:** {ok_count} tam, {partial_count} kısmi, {missing_count} veri yok "
        f"({len(scored)} madde skorlandı)",
        "",
        "> Bu rapor otomatik üretilmiştir ve yatırım tavsiyesi değildir. Skorlar veri ağırlıklı",
        "> tahminlerdir; kesinlik iddiası taşımaz.",
        "",
        "## 10 Ana Analiz",
        "",
        "| Analiz | Durum | Skor | Güven | Özet |",
        "| --- | --- | --- | --- | --- |",
    ]
    for analysis in analyses:
        lines.append(
            f"| {analysis.title} | {STATUS_LABELS.get(analysis.status, analysis.status)} | "
            f"{score(analysis.score)} | {analysis.confidence:.2f} | {_summary_cell(analysis.summary)} |"
        )
    lines.append("")

    for analysis in analyses:
        lines.append(f"### {analysis.title}")
        lines.append("")
        lines.append(analysis.summary or "_Özet yok_")
        lines.append("")
        reasons = (analysis.data or {}).get("reasons")
        if reasons:
            lines.append("**Nedenler:**")
            for reason in reasons[:10]:
                lines.append(f"- {reason}")
            if len(reasons) > 10:
                lines.append(f"- … ve {len(reasons) - 10} neden daha")
            lines.append("")
        if analysis.sources:
            lines.append(
                "**Kaynaklar:** " + ", ".join(sorted({s.name for s in analysis.sources}))
            )
            lines.append("")

    lines.extend(
        [
            "## 66 Maddelik Araştırma Tablosu",
            "",
            "| # | Madde | Durum | Skor | Güven | Özet |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for item in items:
        lines.append(
            f"| {item.item_id} | {item.title_tr} | {STATUS_LABELS.get(item.status, item.status)} | "
            f"{score(item.score)} | {item.confidence:.2f} | {_summary_cell(item.summary)} |"
        )
    lines.append("")

    lines.append("## Madde Detayları")
    lines.append("")
    for item in items:
        lines.append(f"### {item.item_id}. {item.title_tr}")
        lines.append("")
        lines.append(f"- **Durum:** {STATUS_LABELS.get(item.status, item.status)}")
        lines.append(f"- **Skor / Güven:** {score(item.score)} / {item.confidence:.2f}")
        lines.append(f"- **Özet:** {item.summary or '—'}")
        reasons = (item.data or {}).get("reasons")
        if reasons:
            lines.append("- **Nedenler:** " + "; ".join(str(reason) for reason in reasons[:6]))
        if item.sources:
            lines.append(
                "- **Kaynaklar:** " + ", ".join(sorted({s.name for s in item.sources}))
            )
        if item.warnings:
            lines.append("- **Uyarılar:** " + "; ".join(item.warnings))
        lines.append("")

    lines.extend(["## Kullanılan Kaynaklar", ""])
    for source in sorted({s.name for s in run.sources}):
        lines.append(f"- {source}")
    lines.append("")

    if prompt:
        lines.extend(
            [
                "## Prompt Dosyası",
                "",
                "Harici AI'a verilecek prompt aynı isimli `_prompt.txt` dosyasındadır.",
                "",
            ]
        )

    lines.extend(
        [
            "## Metodoloji ve Sınırlamalar",
            "",
            "- Veriler ücretsiz API katmanlarından toplanır (CoinGecko, Binance, Coinalyze, DefiLlama,",
            "  CryptoPanic, RSS, GDELT, alternative.me, Reddit, Google Trends, Blockchain.com,",
            "  mempool.space, Blockchair, Blockscout, Etherscan, yfinance, FRED, Deribit).",
            "- Her madde veri + kaynak + güven ile raporlanır; verisi olmayan maddeler ortalamaya",
            "  dahil edilmez ve raporda açıkça işaretlenir.",
            "- Skorlar -1 (güçlü negatif) ile +1 (güçlü pozitif) arasındadır; ağırlıklı ortalama",
            "  güven katsayısı ile hesaplanır.",
            "- Sayılar tr-TR biçiminde gösterilir (binlik ayracı nokta, ondalık virgül).",
            "",
        ]
    )
    for note in run.notes:
        lines.append(f"> Not: {note}")
    lines.append("")
    return "\n".join(lines)
