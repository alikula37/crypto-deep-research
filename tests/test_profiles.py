"""Skorlama profili testleri: kategori carpanlari ve agirlikli skora etkisi."""

from crypto_deep_research.deep_research.engine import compute_weighted_score
from crypto_deep_research.deep_research.profiles import (
    DEFAULT_PROFILE,
    normalize_profile,
    profile_summary,
    weight_multipliers,
)
from crypto_deep_research.deep_research.registry import load_registry
from crypto_deep_research.models import ItemResult


def _item(item_id: int, category: str, score: float, confidence: float = 1.0, weight: float = 1.0):
    return ItemResult(
        item_id=item_id,
        title_tr=f"Madde {item_id}",
        key=f"item_{item_id}",
        title=f"Madde {item_id}",
        status="ok",
        score=score,
        confidence=confidence,
        weight=weight,
        category=category,
    )


def test_normalize_profile():
    assert normalize_profile(None) == DEFAULT_PROFILE
    assert normalize_profile("AGGRESSIVE") == "aggressive"
    assert normalize_profile("bilinmeyen") == DEFAULT_PROFILE


def test_profile_summary_has_three_profiles():
    keys = {entry["key"] for entry in profile_summary()}
    assert keys == {"balanced", "conservative", "aggressive"}


def test_conservative_downweights_sentiment_and_news():
    registry = load_registry()
    multipliers = weight_multipliers("conservative", registry)
    sentiment = next(item for item in registry if item.category == "Sentiment" and item.weight > 0)
    fundamental = next(item for item in registry if item.category == "Temel" and item.weight > 0)
    assert multipliers[sentiment.id] < 1.0
    assert multipliers[fundamental.id] > 1.0


def test_profile_changes_weighted_score():
    """Haber sinyali pozitifken muhafazakar profil skoru dusurmeli; agresif yukseltmeli."""
    items = [
        _item(4, "Haber", 1.0),
        _item(2, "Temel", -0.2),
    ]
    base = compute_weighted_score(items)
    conservative = compute_weighted_score(
        items, multipliers={4: 0.6, 2: 1.3}
    )
    aggressive = compute_weighted_score(items, multipliers={4: 1.1, 2: 0.8})
    assert conservative < base < aggressive


def test_balanced_profile_is_identity():
    registry = load_registry()
    assert weight_multipliers("balanced", registry) == {}
    assert weight_multipliers("bilinmeyen", registry) == {}
