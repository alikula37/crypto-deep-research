"""Analiz ve skorlama testleri (ag erisimi olmadan)."""

from crypto_deep_research.deep_research.engine import (
    compute_weighted_score,
    expected_range,
    probabilities,
)
from crypto_deep_research.models import ItemResult


def _item(item_id: int, score, confidence, weight=1.0, status="ok") -> ItemResult:
    return ItemResult(
        item_id=item_id,
        title_tr=f"Madde {item_id}",
        key=f"item_{item_id}",
        title=f"Madde {item_id}",
        status=status,
        score=score,
        confidence=confidence,
        weight=weight,
    )


def test_weighted_score_ignores_missing_and_zero_confidence():
    items = [
        _item(1, 1.0, 1.0),
        _item(2, -1.0, 1.0),
        _item(3, None, 0.0),
        _item(4, 0.5, 0.0),
    ]
    assert compute_weighted_score(items) == 0.0


def test_weighted_score_uses_confidence_as_weight():
    items = [_item(1, 1.0, 0.8), _item(2, -1.0, 0.2)]
    score = compute_weighted_score(items)
    assert score == 0.6


def test_probabilities_bounds():
    assert probabilities(1.0) == (85.0, 15.0)
    assert probabilities(-1.0) == (15.0, 85.0)
    assert probabilities(None) == (50.0, 50.0)


def test_shared_signal_group_counts_once():
    """Ayni grubu paylasan maddeler tek sinyal gibi (en yuksek agirlikla) sayilir."""
    items = [
        _item(1, 1.0, 1.0, weight=1.0),
        _item(7, 1.0, 1.0, weight=1.0),
        _item(2, 0.0, 1.0, weight=2.0),
    ]
    factors = {1: 0.5, 7: 0.5}
    assert compute_weighted_score(items, group_factors=factors) == 0.3333
    assert compute_weighted_score(items) == 0.5


def test_partial_status_gets_half_weight():
    items = [
        _item(1, 1.0, 1.0, weight=1.0, status="partial"),
        _item(2, 0.0, 1.0, weight=1.0, status="ok"),
    ]
    assert compute_weighted_score(items) == 0.3333
    assert compute_weighted_score(items, partial_penalty=1.0) == 0.5


def test_group_factors_from_registry():
    from crypto_deep_research.deep_research.engine import compute_group_factors
    from crypto_deep_research.deep_research.registry import load_registry

    factors = compute_group_factors(load_registry())
    group_ids = [item.id for item in load_registry() if item.scoring_group == "analysis:technical"]
    assert group_ids == [1, 7, 14, 15, 16, 17, 19]
    assert all(item_id in factors for item_id in group_ids)
    # Grup katkisi, en yuksek agirlikli uyenin agirligina esit olmali.
    total = sum(
        item.weight * factors[item.id]
        for item in load_registry()
        if item.id in group_ids
    )
    assert abs(total - 1.0) < 1e-9


def test_expected_range_contains_price():
    low, high = expected_range(100.0, 2.5, 0.3)
    assert low < 100 < high
    assert round(high - low, 6) > 0


def test_expected_range_zero_score_symmetric():
    low, high = expected_range(100.0, 2.0, 0.0)
    assert abs((100 - low) - (high - 100)) < 1e-6
