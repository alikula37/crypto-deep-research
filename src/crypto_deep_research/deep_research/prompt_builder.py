"""66 madde icin Turkce deep research prompt'u uretir (tr-TR bicim)."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from crypto_deep_research.context.control_plane import ContextControlPlane
from crypto_deep_research.formatting import (
    price,
    price_range,
    round_floats,
    score,
)
from crypto_deep_research.models import AnalysisResult, ItemResult

TEMPLATE_INTRO = """Kripto Yapay Zeka Analizi

Bugünün tarihi {date} saat {time}. {name} ({symbol}) varlığının güncel fiyatı {price}.
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

STATUS_LABELS = {
    "ok": "Tam",
    "partial": "Kısmi",
    "no_data": "Veri yok",
    "error": "Hata",
}

DATA_LIMIT = 700


def _compact_json(obj: Any, limit: int = DATA_LIMIT) -> str:
    """JSON'u e-notation'siz ve sinirli uzunlukta metne cevirir."""
    text = json.dumps(obj, ensure_ascii=False, default=str)
    if len(text) <= limit:
        return text
    if isinstance(obj, dict):
        shallow: dict[str, Any] = {}
        for key, value in obj.items():
            if isinstance(value, dict):
                shallow[key] = {k: v for k, v in list(value.items())[:3]}
            elif isinstance(value, list):
                shallow[key] = value[:2]
            else:
                shallow[key] = value
        text = json.dumps(shallow, ensure_ascii=False, default=str)
        if len(text) <= limit:
            return text + " … (listeler kısaltıldı)"
    return text[:limit] + " … (kısaltıldı)"


def _compact_data(data: dict[str, Any], limit: int = DATA_LIMIT) -> str:
    """Veriyi JSON guvenli (e-notation'siz) ve sinirli uzunlukta metne cevirir."""
    if not data:
        return ""
    filtered = {key: value for key, value in data.items() if key != "reasons"}
    if not filtered:
        return ""
    return _compact_json(round_floats(filtered), limit)


def _format_item(item: ItemResult, data_text: str) -> str:
    lines = [
        f"{item.item_id}. {item.title_tr} | durum: {STATUS_LABELS.get(item.status, item.status)} | "
        f"skor: {score(item.score)} | güven: {item.confidence:.2f}"
    ]
    if item.summary:
        lines.append(f"   Bulgular: {item.summary}")
    reasons = (item.data or {}).get("reasons")
    if reasons:
        lines.append("   Nedenler: " + "; ".join(str(reason) for reason in reasons[:6]))
    if data_text:
        lines.append(f"   Veri: {data_text}")
    if item.sources:
        lines.append("   Kaynaklar: " + ", ".join(sorted({s.name for s in item.sources})))
    if item.warnings:
        lines.append("   Uyarılar: " + "; ".join(item.warnings))
    return "\n".join(lines)


def _prepare_items(items: list[ItemResult]) -> list[str]:
    """Maddeleri, tekrar eden veri bloklarini tekillestirerek metne cevirir."""
    seen_indicators: dict[str, int] = {}
    rendered: list[str] = []
    for item in items:
        data = dict(item.data or {})
        indicators = data.pop("indicators", None)
        parts: list[str] = []
        if indicators is not None:
            blob = json.dumps(round_floats(indicators), ensure_ascii=False, sort_keys=True)
            if blob in seen_indicators:
                parts.append(f'{{"indicators": "bkz. Madde {seen_indicators[blob]}"}}')
            else:
                seen_indicators[blob] = item.item_id
                parts.append(
                    _compact_json({"indicators": round_floats(indicators)}, DATA_LIMIT)
                )
        rest = _compact_data(data)
        if rest:
            parts.append(rest)
        rendered.append(_format_item(item, " | ".join(parts)))
    return rendered


def build_prompt(
    run,
    analyses: list[AnalysisResult],
    items: list[ItemResult],
    control_plane: ContextControlPlane | None = None,
) -> str:
    now: datetime = run.created_at
    sections: list[str] = [
        TEMPLATE_INTRO.format(
            date=now.strftime("%d.%m.%Y"),
            time=now.strftime("%H:%M"),
            name=run.coin.name,
            symbol=run.coin.symbol.upper(),
            price=price(run.current_price),
        ),
        "=" * 70,
        "10 ANA ANALİZ ÖZETİ",
        "=" * 70,
    ]
    for analysis in analyses:
        sections.append(
            f"[{analysis.key}] {analysis.title} ({STATUS_LABELS.get(analysis.status, analysis.status)}, "
            f"skor: {score(analysis.score)}, güven: {analysis.confidence:.2f})\n{analysis.summary}"
        )
        if analysis.sources:
            sections.append("Kaynaklar: " + ", ".join(sorted({s.name for s in analysis.sources})))

    sections.append("=" * 70)
    sections.append("66 KRİTERLİK ARAŞTIRMA BULGULARI")
    sections.append("=" * 70)
    sections.extend(_prepare_items(items))

    sections.append("=" * 70)
    sections.append("SİSTEM TAHMİNİ (veri ağırlıklı, garanti değil)")
    sections.append("=" * 70)
    sections.append(
        f"Ağırlıklı skor: {score(run.weighted_score)}\n"
        f"Yükseliş olasılığı: %{run.up_probability:.1f}\n"
        f"Düşüş olasılığı: %{run.down_probability:.1f}\n"
        f"Beklenen fiyat aralığı: {price_range(run.expected_low, run.expected_high)}\n"
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
