"""Rapor cikti kalitesi: e-notation, None ve yarim kelime olmamali."""


from crypto_deep_research.deep_research.report import render_report
from crypto_deep_research.models import AnalysisResult, CoinRef, ItemResult, ResearchRun


def _run() -> ResearchRun:
    return ResearchRun(
        run_id="abc123",
        coin=CoinRef(id="pepe", symbol="pepe", name="Pepe"),
        timeframe="1d",
        lookback_days=15,
        weighted_score=-0.0368,
        up_probability=48.3,
        down_probability=51.7,
        expected_low=3.03e-06,
        expected_high=3.59e-06,
        current_price=3.31e-06,
        notes=["test notu"],
    )


def test_report_micro_price_and_range_formatted():
    markdown = render_report(_run(), [], [])
    assert "$0,00000331" in markdown
    assert "$0,00000303 – $0,00000359" in markdown
    assert "e-06" not in markdown
    assert "None" not in markdown


def test_report_no_mid_word_truncation():
    item = ItemResult(
        item_id=1,
        title_tr="Teknik Analiz",
        key="item_1",
        title="Teknik Analiz",
        status="ok",
        summary=("Mum formasyonları: Shooting Star (tepe dönüş sinyali). " * 8),
        score=0.1,
        confidence=0.5,
    )
    markdown = render_report(_run(), [], [item])
    assert "Shootin " not in markdown
    table_rows = [line for line in markdown.splitlines() if line.startswith("| 1 |")]
    assert table_rows
    assert "…" in table_rows[0]
    cut = table_rows[0].rsplit("|", 2)[0]
    assert not cut.rstrip().endswith(("Sh", "Gra", "Fo", "Wh"))


def test_report_status_labels_turkish():
    item = ItemResult(
        item_id=2,
        title_tr="Temel Analiz",
        key="item_2",
        title="Temel Analiz",
        status="no_data",
        summary="veri yok",
        score=None,
        confidence=0.0,
    )
    analysis = AnalysisResult(key="revenue", title="Gelirler", status="no_data", summary="yok")
    markdown = render_report(_run(), [analysis], [item])
    assert "Veri yok" in markdown
    assert "—" in markdown
