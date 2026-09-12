"""Teknik göstergeler ve formasyon tespitleri (pandas ile, hariçi TA kutuphanesi yok)."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from crypto_deep_research.models import Kline


def to_dataframe(klines: list[Kline]) -> pd.DataFrame:
    if not klines:
        return pd.DataFrame(columns=["ts", "open", "high", "low", "close", "volume"])
    df = pd.DataFrame([k.model_dump() for k in klines])
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df = df.set_index("ts").sort_index()
    return df.astype(float)


def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(period, min_periods=max(2, period // 2)).mean()


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50)


def macd(
    series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[pd.Series, pd.Series, pd.Series]:
    macd_line = ema(series, fast) - ema(series, slow)
    signal_line = ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def bollinger(series: pd.Series, period: int = 20, num_std: float = 2.0):
    middle = sma(series, period)
    std = series.rolling(period, min_periods=max(2, period // 2)).std()
    upper = middle + num_std * std
    lower = middle - num_std * std
    width = (upper - lower) / middle.replace(0, np.nan)
    position = (series - lower) / (upper - lower).replace(0, np.nan)
    return middle, upper, lower, width, position


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def stochastic(df: pd.DataFrame, k_period: int = 14, d_period: int = 3):
    low_min = df["low"].rolling(k_period).min()
    high_max = df["high"].rolling(k_period).max()
    k = 100 * (df["close"] - low_min) / (high_max - low_min).replace(0, np.nan)
    d = k.rolling(d_period).mean()
    return k, d


def obv(df: pd.DataFrame) -> pd.Series:
    direction = np.sign(df["close"].diff()).fillna(0)
    return (direction * df["volume"]).cumsum()


def find_pivots(
    df: pd.DataFrame, left: int = 3, right: int = 3, max_levels: int = 8
) -> dict[str, list[float]]:
    """Yerel tepe/dip noktaları (destek-direnç adaylari)."""
    highs: list[tuple[int, float]] = []
    lows: list[tuple[int, float]] = []
    high_values = df["high"].values
    low_values = df["low"].values
    for i in range(left, len(df) - right):
        window_high = high_values[i - left : i + right + 1]
        window_low = low_values[i - left : i + right + 1]
        if high_values[i] == window_high.max():
            highs.append((i, float(high_values[i])))
        if low_values[i] == window_low.min():
            lows.append((i, float(low_values[i])))
    recent_highs = [value for _, value in highs[-40:]]
    recent_lows = [value for _, value in lows[-40:]]
    return {
        "resistance": _cluster_levels(sorted(recent_highs, reverse=True))[:max_levels],
        "support": _cluster_levels(sorted(recent_lows))[:max_levels],
    }


def _cluster_levels(levels: list[float], tolerance: float = 0.012) -> list[float]:
    clusters: list[list[float]] = []
    for level in levels:
        if clusters and abs(level - clusters[-1][-1]) / max(clusters[-1][-1], 1e-9) < tolerance:
            clusters[-1].append(level)
        else:
            clusters.append([level])
    return [round(float(np.mean(cluster)), 6) for cluster in clusters]


def volume_profile(df: pd.DataFrame, bins: int = 30) -> list[dict[str, Any]]:
    """Fiyat bazlı hacim profili (destek/direnç yoğunluğu)."""
    if df.empty or df["volume"].sum() == 0:
        return []
    low, high = float(df["low"].min()), float(df["high"].max())
    if high <= low:
        return []
    edges = np.linspace(low, high, bins + 1)
    labels = (df["close"] - low) / (high - low) * bins
    bucket = labels.clip(0, bins - 1).astype(int)
    grouped = df.groupby(bucket)["volume"].sum()
    total = grouped.sum()
    profile = []
    for idx, volume in grouped.items():
        profile.append(
            {
                "price_low": round(float(edges[idx]), 6),
                "price_high": round(float(edges[idx + 1]), 6),
                "volume": float(volume),
                "share": round(float(volume / total), 4) if total else 0.0,
            }
        )
    profile.sort(key=lambda item: item["share"], reverse=True)
    return profile


def fibonacci_levels(high: float, low: float) -> dict[str, float]:
    diff = high - low
    return {
        "0.0": high,
        "0.236": high - 0.236 * diff,
        "0.382": high - 0.382 * diff,
        "0.5": high - 0.5 * diff,
        "0.618": high - 0.618 * diff,
        "0.786": high - 0.786 * diff,
        "1.0": low,
        "1.272": low - 0.272 * diff,
        "1.618": low - 0.618 * diff,
    }


def candle_patterns(df: pd.DataFrame) -> list[str]:
    """Son mumlarda temel formasyon tespiti."""
    patterns: list[str] = []
    if len(df) < 3:
        return patterns
    last = df.iloc[-1]
    prev = df.iloc[-2]
    body = abs(last["close"] - last["open"])
    full_range = max(last["high"] - last["low"], 1e-9)
    upper_wick = last["high"] - max(last["close"], last["open"])
    lower_wick = min(last["close"], last["open"]) - last["low"]

    if body / full_range < 0.1:
        patterns.append("Doji (kararsızlık)")
    if lower_wick > body * 2 and upper_wick < body:
        patterns.append("Hammer (dip dönüş sinyali)")
    if upper_wick > body * 2 and lower_wick < body:
        patterns.append("Shooting Star (tepe dönüş sinyali)")
    prev_body = abs(prev["close"] - prev["open"])
    if last["close"] > last["open"] and prev["close"] < prev["open"] and body > prev_body:
        patterns.append("Bullish Engulfing")
    if last["close"] < last["open"] and prev["close"] > prev["open"] and body > prev_body:
        patterns.append("Bearish Engulfing")
    if len(df) >= 3:
        three_closes = df["close"].tail(3).tolist()
        if three_closes[0] < three_closes[1] < three_closes[2]:
            patterns.append("Üç beyaz asker (yükseliş)")
        if three_closes[0] > three_closes[1] > three_closes[2]:
            patterns.append("Üç siyah karga (düşüş)")
    return patterns


def detect_chart_patterns(df: pd.DataFrame) -> list[str]:
    """Basit grafik formasyon tespiti (çift tepe/dip, kanal, üçgen yaklaşımi)."""
    patterns: list[str] = []
    if len(df) < 60:
        return patterns
    window = df.tail(90)
    pivots = find_pivots(window, left=4, right=4)
    highs = [h for h in pivots["resistance"][:6]]
    lows = [s for s in pivots["support"][:6]]
    current = float(window["close"].iloc[-1])
    for i in range(len(highs) - 1):
        for j in range(i + 1, len(highs)):
            if abs(highs[i] - highs[j]) / max(highs[j], 1e-9) < 0.02 and current < highs[j] * 0.98:
                patterns.append("Çift tepe (Double Top)")
                break
    for i in range(len(lows) - 1):
        for j in range(i + 1, len(lows)):
            if abs(lows[i] - lows[j]) / max(lows[j], 1e-9) < 0.02 and current > lows[j] * 1.02:
                patterns.append("Çift dip (Double Bottom)")
                break
    closes = window["close"]
    if closes.iloc[-1] > closes.rolling(30).max().iloc[-2]:
        patterns.append("30 periyot kırılımı (breakout)")
    if closes.iloc[-1] < closes.rolling(30).min().iloc[-2]:
        patterns.append("30 periyot aşağı kırılımı (breakdown)")
    deduped: list[str] = []
    for pattern in patterns:
        if pattern not in deduped:
            deduped.append(pattern)
    return deduped


def indicator_snapshot(df: pd.DataFrame) -> dict[str, Any]:
    """Teknik göstergelerin son değerleri ve sinyalleri."""
    close = df["close"]
    out: dict[str, Any] = {}
    out["price"] = float(close.iloc[-1])
    out["ema_20"] = float(ema(close, 20).iloc[-1])
    out["ema_50"] = float(ema(close, 50).iloc[-1]) if len(df) >= 30 else None
    out["ema_200"] = float(ema(close, 200).iloc[-1]) if len(df) >= 120 else None
    out["sma_50"] = float(sma(close, 50).iloc[-1]) if len(df) >= 30 else None
    out["sma_200"] = float(sma(close, 200).iloc[-1]) if len(df) >= 120 else None
    rsi_series = rsi(close)
    out["rsi_14"] = float(rsi_series.iloc[-1])
    macd_line, signal_line, histogram = macd(close)
    out["macd"] = float(macd_line.iloc[-1])
    out["macd_signal"] = float(signal_line.iloc[-1])
    out["macd_histogram"] = float(histogram.iloc[-1])
    out["macd_histogram_prev"] = float(histogram.iloc[-2]) if len(histogram) > 1 else 0.0
    middle, upper, lower, width, position = bollinger(close)
    out["bb_middle"] = float(middle.iloc[-1]) if not np.isnan(middle.iloc[-1]) else None
    out["bb_upper"] = float(upper.iloc[-1]) if not np.isnan(upper.iloc[-1]) else None
    out["bb_lower"] = float(lower.iloc[-1]) if not np.isnan(lower.iloc[-1]) else None
    out["bb_width"] = float(width.iloc[-1]) if not np.isnan(width.iloc[-1]) else None
    out["bb_position"] = float(position.iloc[-1]) if not np.isnan(position.iloc[-1]) else None
    atr_series = atr(df)
    out["atr_14"] = float(atr_series.iloc[-1])
    out["atr_pct"] = float(atr_series.iloc[-1] / close.iloc[-1] * 100) if close.iloc[-1] else None
    if "volume" in df and df["volume"].sum() > 0:
        obv_series = obv(df)
        out["obv_change_20"] = float(obv_series.diff(20).iloc[-1])
        volume_ma = df["volume"].rolling(20).mean()
        out["volume_vs_ma20"] = (
            float(df["volume"].iloc[-1] / volume_ma.iloc[-1])
            if volume_ma.iloc[-1]
            else None
        )
    k, d = stochastic(df)
    out["stoch_k"] = float(k.iloc[-1]) if not np.isnan(k.iloc[-1]) else None
    out["stoch_d"] = float(d.iloc[-1]) if not np.isnan(d.iloc[-1]) else None
    return out


def indicator_score(snapshot: dict[str, Any]) -> tuple[float, float, list[str]]:
    """Göstergelerden -1..1 skor, güven ve gerekçe üretir."""
    signals: list[str] = []
    score = 0.0
    weight = 0.0
    price = snapshot.get("price") or 0

    rsi_value = snapshot.get("rsi_14")
    if rsi_value is not None:
        weight += 1
        if rsi_value < 30:
            score += 0.8
            signals.append(f"RSI {rsi_value:.1f} aşırı satım (dönüş potansiyeli)")
        elif rsi_value > 70:
            score -= 0.8
            signals.append(f"RSI {rsi_value:.1f} aşırı alım (düzeltme riski)")
        else:
            score += (50 - abs(rsi_value - 50)) / 100 * (0.4 if rsi_value > 50 else -0.4)
            signals.append(f"RSI {rsi_value:.1f} nötr")

    histogram = snapshot.get("macd_histogram")
    histogram_prev = snapshot.get("macd_histogram_prev")
    if histogram is not None and histogram_prev is not None:
        weight += 1
        if histogram > 0 and histogram > histogram_prev:
            score += 0.7
            signals.append("MACD pozitif ve güçleniyor")
        elif histogram > 0:
            score += 0.3
            signals.append("MACD pozitif ancak zayıflıyor")
        elif histogram < 0 and histogram < histogram_prev:
            score -= 0.7
            signals.append("MACD negatif ve zayıflıyor")
        else:
            score -= 0.3
            signals.append("MACD negatif ancak toparlaniyor")

    ema200 = snapshot.get("ema_200") or snapshot.get("sma_200")
    if ema200 and price:
        weight += 1
        if price > ema200:
            score += 0.5
            signals.append("Fiyat 200 EMA üzerinde (uzun trend pozitif)")
        else:
            score -= 0.5
            signals.append("Fiyat 200 EMA altında (uzun trend negatif)")

    ema50 = snapshot.get("ema_50") or snapshot.get("sma_50")
    if ema50 and price:
        weight += 1
        if price > ema50:
            score += 0.3
            signals.append("Fiyat 50 EMA üzerinde (orta trend pozitif)")
        else:
            score -= 0.3
            signals.append("Fiyat 50 EMA altında (orta trend negatif)")

    position = snapshot.get("bb_position")
    if position is not None:
        weight += 1
        if position < 0.05:
            score += 0.5
            signals.append("Bollinger alt bandinda")
        elif position > 0.95:
            score -= 0.5
            signals.append("Bollinger üst bandinda")

    stoch_k = snapshot.get("stoch_k")
    if stoch_k is not None:
        weight += 0.5
        if stoch_k < 20:
            score += 0.3
            signals.append("Stochastic aşırı satım")
        elif stoch_k > 80:
            score -= 0.3
            signals.append("Stochastic aşırı alım")

    volume_ratio = snapshot.get("volume_vs_ma20")
    if volume_ratio is not None:
        weight += 0.5
        if volume_ratio > 1.5:
            signals.append(f"Hacim 20 gün ortalamasının {volume_ratio:.1f}x üzerinde")

    if weight == 0:
        return 0.0, 0.0, signals
    return max(-1.0, min(1.0, score / weight)), min(0.8, weight / 4.5), signals


def compute_levels(df: pd.DataFrame, current_price: float) -> dict[str, Any]:
    """Destek/direnç, fibonacci ve hacim profili seviyeleri."""
    window = df.tail(180) if len(df) > 180 else df
    pivots = find_pivots(window)
    high = float(window["high"].max())
    low = float(window["low"].min())
    fib = fibonacci_levels(high, low)
    profile = volume_profile(window, bins=30)
    supports = sorted([level for level in pivots["support"] if level < current_price], reverse=True)
    resistances = sorted([level for level in pivots["resistance"] if level > current_price])
    nearest_support = supports[0] if supports else fib.get("0.618")
    nearest_resistance = resistances[0] if resistances else fib.get("0.236")
    return {
        "support": supports[:5],
        "resistance": resistances[:5],
        "nearest_support": nearest_support,
        "nearest_resistance": nearest_resistance,
        "swing_high": high,
        "swing_low": low,
        "fibonacci": fib,
        "volume_profile_top": profile[:6],
        "distance_to_support_pct": round((current_price / nearest_support - 1) * 100, 2)
        if nearest_support
        else None,
        "distance_to_resistance_pct": round((nearest_resistance / current_price - 1) * 100, 2)
        if nearest_resistance
        else None,
    }
