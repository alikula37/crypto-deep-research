"""Skorlama profilleri: kategori agirliklarini yatirim tarzina gore olcekler."""

from __future__ import annotations

from typing import Any

PROFILES: dict[str, dict[str, Any]] = {
    "balanced": {
        "label": "Dengeli",
        "description": "Tüm sinyaller kanıt gücüne göre dengeli ağırlıkta sayılır.",
        "category_multipliers": {},
    },
    "conservative": {
        "label": "Muhafazakâr",
        "description": "Doğrulanmış veri (temel, zincir-üstü, makro) öne çıkar; haber, sosyal ve türev gürültüsü kısılır.",
        "category_multipliers": {
            "Temel": 1.3,
            "Zincir-Üstü": 1.3,
            "Makro": 1.2,
            "Piyasa": 1.1,
            "Teknik": 0.8,
            "Türev": 0.7,
            "Haber": 0.6,
            "Sentiment": 0.5,
            "Kantitatif": 0.6,
            "Alternatif": 0.0,
            "AI": 0.0,
            "Meta": 0.0,
        },
    },
    "aggressive": {
        "label": "Agresif",
        "description": "Momentum ve kısa vade sinyalleri (teknik, türev, sentiment) öne çıkar; yavaş makro geri plana düşer.",
        "category_multipliers": {
            "Teknik": 1.4,
            "Türev": 1.3,
            "Sentiment": 1.2,
            "Haber": 1.1,
            "Piyasa": 1.2,
            "Kantitatif": 1.1,
            "Zincir-Üstü": 0.9,
            "Temel": 0.8,
            "Makro": 0.7,
        },
    },
}

DEFAULT_PROFILE = "balanced"


def normalize_profile(name: str | None) -> str:
    if not name:
        return DEFAULT_PROFILE
    key = name.strip().lower()
    return key if key in PROFILES else DEFAULT_PROFILE


def profile_summary() -> list[dict[str, str]]:
    return [
        {"key": key, "label": value["label"], "description": value["description"]}
        for key, value in PROFILES.items()
    ]


def weight_multipliers(profile: str, items: list[Any]) -> dict[int, float]:
    """Profilin kategori carpanlarini madde id'lerine uygular (dengeli: bos sozluk)."""
    config = PROFILES[normalize_profile(profile)]
    multipliers: dict[str, float] = config.get("category_multipliers") or {}
    if not multipliers:
        return {}
    return {item.id: multipliers.get(item.category, 1.0) for item in items}
