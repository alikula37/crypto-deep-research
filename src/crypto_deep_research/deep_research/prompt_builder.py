"""66 madde için Turkce deep research prompt'u üretir."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from crypto_deep_research.context.control_plane import ContextControlPlane
from crypto_deep_research.models import AnalysisResult, ItemResult

TEMPLATE_INTRO = """Kripto Yapay Zeka Analizi

Bugünün tarihi {date} saat {time}. {name} ({symbol}) varlığının güncel fiyatı {price} dolar.
Sana aşağıda maddeler halinde sıralayacağım verileri, en çok doğru bilgi veren, bilinen ve güvenilir
sitelerde araştırdığında {name} varlığının GÜN içinde nasıl bir fiyat hareketi yapacağını değerlendir:

- Yüzde kaç yükselir? Yüzde kaç düşer?
- Yükselme ihtimali yüzde kaçtır? Düşme ihtimali yüzde kaçtır?
- Beklenen fiyat aralığı nedir?

Fiyat hareketlerini tahmin etmek için aşağıda sıraladığım bütün araştırma yöntemlerinden tek tek bilgi al.
Kesin bilgi veremeyeceğini biliyorum; sadece en yüksek başarılı tahmini yapmanı istiyorum.
Verilen bilgilerin doğruluk oranına ve başarısına göre değerlendirme yapacağım.
Bu bilgiler yatırım kararı için değil, akademik bir tez çalışması için kullanılacaktır.
Tek cümlede en net tahminini söyle ve sadece bir tahmin ver.

Aşağıdaki 66 maddenin tamamını, verilen veri ve kaynaklarla tek tek ele al; sonra her madde için
yükseliş/düşüş yönünde bir yüzde puanı biçtiğin kısa bir değerlendirme yap. Tüm maddelerin puanlarını
ağırlıklı olarak birleştirip genel bir tahmine ulaş. Veri bulunmayan maddeleri açıkça "veri yok" olarak
işaretle ve ortalamaya katma.
"""


def _format_item(item: ItemResult) -> str:
    lines = [
        f"{item.item_id}. {item.title_tr} | durum: {item.status} | skor: "
        f"{item.score if item.score is not None else 'n/a'} | güven: {item.confidence:.2f}"
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
        lines.append("   Uyarılar: " + "; ".join(item.warnings))
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
        "10 ANA ANALİZ ÖZETİ",
        "=" * 70,
    ]
    for analysis in analyses:
        sections.append(
            f"[{analysis.key}] {analysis.title} ({analysis.status}, skor: {analysis.score}, "
            f"güven: {analysis.confidence:.2f})\n{analysis.summary}"
        )
        if analysis.sources:
            sections.append("Kaynaklar: " + ", ".join(sorted({s.name for s in analysis.sources})))

    sections.append("=" * 70)
    sections.append("66 MADDELİK DETAYLI ARAŞTIRMA")
    sections.append("=" * 70)
    for item in items:
        sections.append(_format_item(item))

    sections.append("=" * 70)
    sections.append("SİSTEM TAHMİNİ (veri ağırlıklı, garanti değil)")
    sections.append("=" * 70)
    sections.append(
        f"Ağırlıklı skor: {run.weighted_score}\n"
        f"Yükseliş olasılığı: %{run.up_probability}\n"
        f"Düşüş olasılığı: %{run.down_probability}\n"
        f"Beklenen fiyat aralığı: {run.expected_low} - {run.expected_high} USD\n"
    )
    if run.sources:
        sections.append(
            "Kullanılan kaynak siteler: " + ", ".join(sorted({s.name for s in run.sources}))
        )
    for note in run.notes:
        sections.append(f"Not: {note}")

    if control_plane is not None:
        contexts = [
            obj
            for obj in control_plane.db.list_contexts(scope_contains=run.coin.id, limit=200)
            if not (obj.kind == "report" and obj.scope.get("run") != run.run_id)
        ]
        managed, stats = control_plane.materialize(contexts)
        sections.append("=" * 70)
        sections.append("YÖNETİLEN CONTEXT (Context Control Plane, önbellek/özet)")
        sections.append("=" * 70)
        sections.append(
            f"Politika özeti: {json.dumps(stats['groups'], ensure_ascii=False)} | "
            f"token: {stats['tokens']}/{stats['budget']}"
        )
        sections.append(managed)

    sections.append(
        "\nSON GÖREV: Yukarıdaki 66 maddeyi tek tek yorumla. Her madde için yükseliş/düşüş yönünde "
        "yüzde tahmini ver. Sonunda tüm maddelerin ortalamasını alarak GÜN için beklenen fiyat "
        "aralığını, yükselme ve düşme ihtimallerini yüzde olarak yaz. En sonunda tek cümlede en net "
        "tahminini söyle."
    )
    return "\n\n".join(sections)
