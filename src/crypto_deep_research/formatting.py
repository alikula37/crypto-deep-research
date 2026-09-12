"""Sayi ve deger bicimlendirme katmani (tr-TR).

Kurallar:
- Bilimsel gosterim (e-notation) asla kullanilmaz.
- Fiyatlar buyukluge gore adaptif hassasiyetle gosterilir.
- Buyuk tutarlar K/M/B/T kisaltmalariyla, tam deger istenirse tam haliyle.
- JSON/veri ciktilari nokta ondalik ile makine-okunur kalir.
"""

from __future__ import annotations

import math
from decimal import Decimal
from typing import Any

DASH = "—"

MONEY_SUFFIXES: tuple[tuple[str, float], ...] = (
    ("T", 1e12),
    ("B", 1e9),
    ("M", 1e6),
    ("K", 1e3),
)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _finite(value: Any) -> float | None:
    if not _is_number(value):
        return None
    number = float(value)
    if not math.isfinite(number):
        return None
    return number


def _plain_sig(value: float, sig: int) -> str:
    """Anlamli basamak sayisina gore, bilimsel gosterim olmadan metin uretir."""
    if value == 0:
        return "0"
    text = f"{value:.{sig}g}"
    if "e" in text or "E" in text:
        text = format(Decimal(text), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _fixed(value: float, digits: int) -> str:
    text = f"{value:.{digits}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _group_int(integer: str) -> str:
    negative = integer.startswith("-")
    digits = integer[1:] if negative else integer
    grouped = ""
    while len(digits) > 3:
        grouped = "." + digits[-3:] + grouped
        digits = digits[:-3]
    grouped = digits + grouped
    return ("-" + grouped) if negative else grouped


def to_tr(text: str) -> str:
    """Nokta ondalikli metni tr-TR bicimine cevirir (1.234,56)."""
    if "." in text:
        integer, decimal = text.split(".", 1)
    else:
        integer, decimal = text, ""
    grouped = _group_int(integer)
    return f"{grouped},{decimal}" if decimal else grouped


def num(value: Any, sig: int = 6, tr: bool = True) -> str:
    """Genel sayi bicimi; e-notation yok, None/NaN -> '—'."""
    number = _finite(value)
    if number is None:
        return DASH
    text = _plain_sig(number, sig)
    return to_tr(text) if tr else text


def price(value: Any, tr: bool = True, currency: str = "$") -> str:
    """Fiyat: buyukluge gore adaptif hassasiyet (PEPE gibi mikro fiyatlar kaybolmaz)."""
    number = _finite(value)
    if number is None:
        return DASH
    abs_value = abs(number)
    if abs_value >= 1000:
        text = _fixed(number, 2)
    elif abs_value >= 1:
        text = _plain_sig(number, 5)
    else:
        text = _plain_sig(number, 4)
    text = to_tr(text) if tr else text
    return f"{currency}{text}" if currency else text


def money(value: Any, tr: bool = True, exact: bool = False, currency: str = "$") -> str:
    """Buyuk tutar: kisaltmali ($303,0M) veya exact=True ile tam deger."""
    number = _finite(value)
    if number is None:
        return DASH
    sign = "-" if number < 0 else ""
    abs_value = abs(number)
    if exact or abs_value < 1000:
        if exact and abs_value >= 1:
            text = _fixed(abs_value, 2)
        else:
            text = _plain_sig(abs_value, 4)
        text = to_tr(text) if tr else text
        return f"{sign}{currency}{text}"
    for suffix, factor in MONEY_SUFFIXES:
        if abs_value >= factor:
            scaled = abs_value / factor
            digits = 2 if scaled < 10 else 1
            text = _fixed(scaled, digits)
            text = to_tr(text) if tr else text
            return f"{sign}{currency}{text}{suffix}"
    return f"{sign}{currency}{_plain_sig(abs_value, 4)}"


def pct(value: Any, tr: bool = True, signed: bool = False, digits: int = 1, cap: float = 9999.0) -> str:
    """Yuzde: isaret opsiyonel, asiri degerler cap ile gosterilir ('>%9.999')."""
    number = _finite(value)
    if number is None:
        return DASH
    if abs(number) > cap:
        cap_text = f"{int(cap)}"
        cap_text = to_tr(cap_text) if tr else cap_text
        sign = "-" if number < 0 else ""
        return f">{sign}%{cap_text}"
    text = f"{abs(number):.{digits}f}".replace(".", ",") if tr else f"{abs(number):.{digits}f}"
    sign = "-" if number < 0 else ("+" if signed else "")
    return f"{sign}%{text}"


def ratio(value: Any, tr: bool = True) -> str:
    """Oran: '×1,24 (+%23,6)' bicimi."""
    number = _finite(value)
    if number is None:
        return DASH
    change = (number - 1) * 100
    return f"×{num(number, 3, tr)} ({pct(change, tr, signed=True)})"


def score(value: Any, tr: bool = True, digits: int = 2) -> str:
    """Skor: '+0,23' / '0,00' / '—'."""
    number = _finite(value)
    if number is None:
        return DASH
    text = f"{abs(number):.{digits}f}"
    text = text.replace(".", ",") if tr else text
    sign = "-" if number < 0 else "+"
    return f"{sign}{text}"


def price_range(low: Any, high: Any, tr: bool = True, currency: str = "$") -> str:
    low_text = price(low, tr=tr, currency=currency)
    high_text = price(high, tr=tr, currency=currency)
    if low_text == DASH or high_text == DASH:
        return DASH
    return f"{low_text} – {high_text}"


def truncate(text: str, limit: int, suffix: str = "…") -> str:
    """Kelime sinirinda kirpar; kelime ortasinda kesmez."""
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    cut = text[: limit - len(suffix)]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip(" ,;:") + suffix


def plain_float_json(value: float, sig: int = 6) -> float | str:
    """JSON icin: kucuk sayilari e-notation'a dusmeden metne cevirir."""
    if not math.isfinite(value):
        return "—"
    if value != 0 and abs(value) < 1e-4:
        text = _plain_sig(value, sig)
        return text if text != "0" else 0
    return float(f"{value:.{sig}g}")


def round_floats(value: Any, sig: int = 6) -> Any:
    """Veriyi JSON guvenli hale getirir: 6 anlamli basamak, e-notation yok."""
    if isinstance(value, bool):
        return value
    if isinstance(value, float):
        return plain_float_json(value, sig)
    if isinstance(value, int):
        return value
    if isinstance(value, dict):
        return {key: round_floats(item, sig) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [round_floats(item, sig) for item in value]
    return value
