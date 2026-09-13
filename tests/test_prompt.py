"""Prompt uretimi ve item degerlendirme testleri."""

from crypto_deep_research.deep_research.prompt_builder import build_prompt
from crypto_deep_research.models import (
    AnalysisResult,
    CoinRef,
    ItemResult,
    ResearchRun,
)


def _run() -> ResearchRun:
    return ResearchRun(
        run_id="abc123",
        coin=CoinRef(id="bitcoin", symbol="btc", name="Bitcoin"),
        timeframe="1d",
        lookback_days=365,
        weighted_score=0.25,
        up_probability=61.3,
        down_probability=38.7,
        expected_low=90000.0,
        expected_high=102000.0,
        current_price=96000.0,
        notes=["test notu"],
    )


def _analysis() -> AnalysisResult:
    return AnalysisResult(
        key="technical",
        title="Teknik Analiz",
        summary="RSI 55",
        score=0.3,
        confidence=0.6,
        data={"reasons": ["test"]},
    )


def _item(item_id: int) -> ItemResult:
    return ItemResult(
        item_id=item_id,
        title_tr=f"Madde {item_id}",
        key=f"item_{item_id}",
        title=f"Madde {item_id}",
        status="ok",
        summary="ozet",
        score=0.1,
        confidence=0.5,
    )


def test_prompt_contains_all_items_and_placeholders():
    prompt = build_prompt(_run(), [_analysis()], [_item(i) for i in range(1, 67)])
    assert "Bitcoin" in prompt
    assert "$96.000" in prompt
    assert "66 KRİTERLİK ARAŞTIRMA BULGULARI" in prompt
    for number in (1, 33, 66):
        assert f"{number}. Madde {number}" in prompt
    assert "Yükseliş olasılığı: %61.3" in prompt
    assert "tek cümlede" in prompt.lower()


def test_prompt_marks_no_data_items():
    item = _item(1)
    item.status = "no_data"
    item.score = None
    item.confidence = 0.0
    prompt = build_prompt(_run(), [], [item])
    assert "veri yok" in prompt.lower() or "no_data" in prompt


def test_prompt_has_no_scientific_notation_or_none():
    item = _item(1)
    item.data = {
        "indicators": {"price": 3.31e-06, "ema_20": 77044.1179303021, "macd": -6.72e-08},
        "reasons": ["test"],
    }
    item.summary = "Fiyat $0,00000331"
    prompt = build_prompt(_run(), [], [item])
    assert "e-06" not in prompt
    assert "e-08" not in prompt
    assert "None" not in prompt
    assert "77044.1" in prompt


def test_prompt_language_instruction():
    base = build_prompt(_run(), [_analysis()], [_item(1)])
    assert "English" not in base
    english = build_prompt(_run(), [_analysis()], [_item(1)], language="en")
    assert "Write your entire response in English" in english
