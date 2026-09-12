"""Bicimlendirme katmani testleri: tr-TR, adaptif hassasiyet, e-notation yasagi."""

from crypto_deep_research.formatting import (
    DASH,
    money,
    num,
    pct,
    price,
    price_range,
    ratio,
    round_floats,
    score,
    to_tr,
    truncate,
)


def test_tr_separators():
    assert to_tr("1234567.89") == "1.234.567,89"
    assert to_tr("1234") == "1.234"
    assert to_tr("0.00000331") == "0,00000331"


def test_price_never_scientific_and_keeps_micro_precision():
    text = price(0.0000033123)
    assert text.startswith("$0,00000331")
    assert "e" not in text.lower()

    assert price(77278.0) == "$77.278"
    assert price(2516.26) == "$2.516,26"


def test_price_handles_none_and_zero():
    assert price(None) == DASH
    assert price(float("nan")) == DASH
    assert price(0.0) == "$0"


def test_money_compact_and_exact():
    assert money(303_034_652) == "$303M"
    assert money(1_551_982_234_870) == "$1,55T"
    assert money(223_017) == "$223K"
    assert money(223_017, exact=True) == "$223.017"


def test_pct_signed_and_cap():
    assert pct(23.56, signed=True) == "+%23,6"
    assert pct(-38.7) == "-%38,7"
    assert pct(113862.5) == ">%9.999"
    assert pct(None) == DASH


def test_ratio_format():
    assert ratio(1.236) == "×1,24 (+%23,6)"
    assert ratio(0.873) == "×0,873 (-%12,7)"


def test_score_format():
    assert score(0.2273) == "+0,23"
    assert score(-0.1046) == "-0,10"
    assert score(None) == DASH


def test_num_no_scientific():
    assert num(3.31e-06) == "0,00000331"
    assert num(1.5e12) == "1,5T" or num(1.5e12) == "1.500.000.000.000"
    assert "e" not in num(1.2273286800148754e-07).lower()


def test_price_range():
    text = price_range(0.00000303, 0.00000359)
    assert "0,00000303" in text and "0,00000359" in text
    assert "e" not in text.lower()


def test_round_floats_json_safe():
    payload = {"small": 3.31e-06, "big": 77044.1179303021, "nested": [{"x": 1.2273286800148754e-07}]}
    rounded = round_floats(payload)
    assert rounded["small"] == "0.00000331"
    assert rounded["big"] == 77044.1
    assert rounded["nested"][0]["x"] == "0.000000122733"


def test_truncate_word_boundary():
    text = "Mum formasyonlari: Shooting Star (tepe donus sinyali). Grafik formasyonlari"
    assert truncate(text, 30).endswith("…")
    assert "Graf" not in truncate(text, 60).split("…")[0]
