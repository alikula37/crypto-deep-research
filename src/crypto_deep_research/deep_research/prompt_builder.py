"""66 madde icin Turkce deep research prompt'u uretir."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from crypto_deep_research.context.control_plane import ContextControlPlane
from crypto_deep_research.models import AnalysisResult, ItemResult

TEMPLATE_INTRO = """Kyripto Yapay Zeka Analizi

Bugunun tarihi {date} saat {time}. {name} ({symbol}) varliginin guncel fiyati {price} dolar.
Sana asagida maddeler halinde siralayacagim verileri, en cok dogru bilgi veren, bilinen ve guvenilir
sitelerde arastirdiginda {name} varliginin GUN icinde nasil bir fiyat haraketi yapacagini degerlendir:

- Yuzde kac yukselir? Yuzde kac duser?
- Yukselme ihtimali yuzde kactir? Dusme ihtimali yuzde kactir?
- Beklenen fiyat araligi nedir?

Fiyat hareketlerini tahmin etmek icin asagida siraladigim butun arastirma yontemlerinden tek tek bilgi al.
Kesin bilgi veremeyecegini biliyorum; sadece en yuksek basarili tahmini yapmani istiyorum.
Verilen bilgilerin dogruluk oranina ve basarisina gore degerlendirme yapacagim.
Bu bilgiler yatirim karari icin degil, akademik bir tez calismasi icin kullanilacaktir.
Tek cumlede en net tahminini soyle ve sadece bir tahmin ver.

Asagidaki 66 maddenin tamamini, verilen veri ve kaynaklarla tek tek ele al; sonra her madde icin
yukselis/dusus yonunde bir yuzde puani bictigin kisa bir degerlendirme yap. Tum maddelerin puanlarini
agirlikli olarak birlestirip genel bir tahmine ulas. Veri bulunmayan maddeleri acikca "veri yok" olarak
isaretle ve ortalamaya katma.
"""


def _format_item(item: ItemResult) -> str:
    lines = [
        f"{item.item_id}. {item.title_tr} | durum: {item.status} | skor: "
        f"{item.score if item.score is not None else 'n/a'} | guven: {item.confidence:.2f}"
    ]
    if item.summary:
        lines.append(f"   Bulgular: {item.summary}")
    reasons = (item.data or {}).get("reasons")
    if reasons:
        lines.append("   Nedenler: " + "; ".join(str(reason) for reason in reasons[:6]))
    details = _compact_data(item.data)
    if details:
        lines.append(f"   Veri: {details}")
    if item.sources:
        lines.append("   Kaynaklar: " + ", ".join(sorted({s.name for s in item.sources})))
    if item.warnings:
        lines.append("   Uyarilar: " + "; ".join(item.warnings))
    return "\n".join(lines)


def _compact_data(data: dict[str, Any], limit: int = 700) -> str:
    if not data:
        return ""
    filtered = {key: value for key, value in data.items() if key != "reasons"}
    if not filtered:
        return ""
    text = json.dumps(filtered, ensure_ascii=False, default=str)
    if len(text) > limit:
        text = text[:limit].rsplit(",", 1)[0] + ", ...}"
    return text


def build_prompt(
    run,
    analyses: list[AnalysisResult],
    items: list[ItemResult],
    control_plane: ContextControlPlane | None = None,
) -> str:
    now: datetime = run.created_at
    price = run.current_price or 0.0
    sections: list[str] = [
        TEMPLATE_INTRO.format(
            date=now.strftime("%d.%m.%Y"),
            time=now.strftime("%H:%M"),
            name=run.coin.name,
            symbol=run.coin.symbol.upper(),
            price=f"{price:,.6f}".rstrip("0").rstrip("."),
        ),
        "=" * 70,
        "10 ANA ANALIZ OZETI",
        "=" * 70,
    ]
    for analysis in analyses:
        sections.append(
            f"[{analysis.key}] {analysis.title} ({analysis.status}, skor: {analysis.score}, "
            f"guven: {analysis.confidence:.2f})\n{analysis.summary}"
        )
        if analysis.sources:
            sections.append("Kaynaklar: " + ", ".join(sorted({s.name for s in analysis.sources})))

    sections.append("=" * 70)
    sections.append("66 MADDELIK DETAYLI ARastirma")
    sections.append("=" * 70)
    for item in items:
        sections.append(_format_item(item))

    sections.append("=" * 70)
    sections.append("SISTEM TAHMINI (veri agirlikli, garanti degil)")
    sections.append("=" * 70)
    sections.append(
        f"Agirlikli skor: {run.weighted_score}\n"
        f"Yukselis olasiligi: %{run.up_probability}\n"
        f"Dusus olasiligi: %{run.down_probability}\n"
        f"Beklenen fiyat araligi: {run.expected_low} - {run.expected_high} USD\n"
    )
    if run.sources:
        sections.append(
            "Kullanilan kaynak siteler: " + ", ".join(sorted({s.name for s in run.sources}))
        )
    for note in run.notes:
        sections.append(f"Not: {note}")

    if control_plane is not None:
        contexts = control_plane.db.list_contexts(scope_contains=run.coin.id, limit=200)
        managed, stats = control_plane.materialize(contexts)
        sections.append("=" * 70)
        sections.append("YONETILEN CONTEXT (Context Control Plane, onbellek/ozet)")
        sections.append("=" * 70)
        sections.append(
            f"Politika ozeti: {json.dumps(stats['groups'], ensure_ascii=False)} | "
            f"token: {stats['tokens']}/{stats['budget']}"
        )
        sections.append(managed)

    sections.append(
        "\nSON GOREV: Yukaridaki 66 maddeyi tek tek yorumla. Her madde icin yukselis/dusus yonunde "
        "yuzde tahmini ver. Sonunda tum maddelerin ortalamasini alarak GUN icin beklenen fiyat "
        "araligini, yukselme ve dusme ihtimallerini yuzde olarak yaz. En sonunda tek cumlede en net "
        "tahminini soyle."
    )
    return "\n\n".join(sections)
