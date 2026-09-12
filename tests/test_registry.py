"""Kayit defteri testleri: 66 madde, benzersiz id, gecerli kaynak tipleri."""

from crypto_deep_research.deep_research.registry import load_registry
from crypto_deep_research.deep_research.specials import SPECIALS


def test_registry_has_66_items():
    items = load_registry()
    assert len(items) == 66
    assert sorted(item.id for item in items) == list(range(1, 67))


def test_registry_source_types_are_valid():
    valid = {"analysis", "special", "news", "unavailable"}
    for item in load_registry():
        assert item.source_type in valid, item
        if item.source_type == "analysis":
            from crypto_deep_research.analysis.engine import ANALYSIS_REGISTRY

            assert item.source_ref in ANALYSIS_REGISTRY, item
        if item.source_type == "special":
            assert item.source_ref in SPECIALS, item
        if item.source_type == "news":
            assert item.query, item


def test_weights_in_range():
    for item in load_registry():
        assert 0 <= item.weight <= 1.0, item


def test_every_item_explains_what_is_researched():
    for item in load_registry():
        assert item.description_tr, f"{item.id}. madde icin aciklama eksik"
        assert len(item.description_tr) >= 30, f"{item.id}. madde aciklamasi cok kisa"


def test_result_from_carries_description_and_note():
    from crypto_deep_research.deep_research.specials import result_from

    spec = next(item for item in load_registry() if item.note)
    result = result_from(spec)
    assert result.description_tr == spec.description_tr
    assert result.note == spec.note
