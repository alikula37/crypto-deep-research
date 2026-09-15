"""Strateji tarayicisi: kanitli kenar ailelerini ayni maliyet ve metriklerle test eder.

Aileler:
1. TSMOM  - zaman serisi momentumu (getiri isareti) + volatilite hedefleme
2. XSMOM  - kesitsel momentum (evrende sirala, ust-k long / alt-k short)
3. CARRY  - fonlama tasiyiciligi (spot long + perp short, delta-notr)
4. BREAK  - Donchian kirilim takibi (giris/cikis kanali + ATR filtre)

Tum seriler gunluk kapanislardir; pozisyonlar bir sonraki gunun getirisine uygulanir
(ileriye bakma yok). Maliyet her pozisyon degisiminde bps olarak dusulur.
"""

from __future__ import annotations

import logging
import math
import statistics
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from crypto_deep_research.analysis.indicators import to_dataframe

logger = logging.getLogger(__name__)

DAY_MS = 86_400_000
TRADING_DAYS = 365


async def load_daily(providers, symbol: str, days: int) -> pd.DataFrame:
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    start_ms = now_ms - (days + 40) * DAY_MS
    klines = await providers.exchange.klines_range(
        symbol, "1d", start_ms=start_ms, end_ms=now_ms
    )
    if not klines:
        return pd.DataFrame()
    return to_dataframe(klines)


def metrics(daily_returns: list[float], btc_returns: list[float] | None = None) -> dict[str, Any]:
    values = [value for value in daily_returns if value is not None]
    if len(values) < 30:
        return {"days": len(values)}
    equity = 1.0
    peak = 1.0
    max_drawdown = 0.0
    for value in values:
        equity *= 1 + value
        peak = max(peak, equity)
        max_drawdown = min(max_drawdown, equity / peak - 1)
    mean = statistics.mean(values)
    deviation = statistics.pstdev(values)
    sharpe = mean / deviation * math.sqrt(TRADING_DAYS) if deviation > 0 else None
    years = len(values) / TRADING_DAYS
    annual = equity ** (1 / years) - 1 if years > 0 and equity > 0 else None
    correlation = None
    if btc_returns:
        paired = [
            (a, b)
            for a, b in zip(values, btc_returns, strict=False)
            if a is not None and b is not None
        ]
        if len(paired) > 30:
            xs, ys = zip(*paired, strict=False)
            mx, my = statistics.mean(xs), statistics.mean(ys)
            cov = sum((x - mx) * (y - my) for x, y in paired) / len(paired)
            sx, sy = statistics.pstdev(xs), statistics.pstdev(ys)
            correlation = round(cov / (sx * sy), 3) if sx > 0 and sy > 0 else None
    return {
        "days": len(values),
        "total_return": round(equity - 1, 4),
        "annual_return": round(annual, 4) if annual is not None else None,
        "sharpe": round(sharpe, 2) if sharpe is not None else None,
        "max_drawdown": round(max_drawdown, 4),
        "vol_annual": round(deviation * math.sqrt(TRADING_DAYS), 4),
        "corr_btc": correlation,
    }


def _pct(series: pd.Series, lookback: int) -> pd.Series:
    return series / series.shift(lookback) - 1


def _vol(returns: pd.Series, window: int = 30) -> pd.Series:
    return returns.rolling(window).std() * math.sqrt(TRADING_DAYS)


def tsmom_series(frame: pd.DataFrame, *, lookback: int = 30, target_vol: float = 0.40,
                 vol_window: int = 30, cost_bps: float = 6.0) -> pd.Series:
    close = frame["close"]
    returns = close.pct_change()
    signal = np.sign(_pct(close, lookback))
    scale = (target_vol / _vol(returns, vol_window)).clip(upper=3.0).fillna(0.0)
    position = (signal * scale).shift(1).fillna(0.0)
    turnover = position.diff().abs().fillna(0.0)
    pnl = position * returns - turnover * cost_bps / 10_000
    return pnl.fillna(0.0)


def tsmom(frame: pd.DataFrame, *, lookback: int = 30, target_vol: float = 0.40,
          vol_window: int = 30, cost_bps: float = 6.0) -> list[float]:
    return tsmom_series(
        frame, lookback=lookback, target_vol=target_vol, vol_window=vol_window, cost_bps=cost_bps
    ).tolist()


def breakout_series(frame: pd.DataFrame, *, entry: int = 20, exit: int = 10,
                    target_vol: float = 0.40, cost_bps: float = 6.0) -> pd.Series:
    close = frame["close"]
    high = frame["high"].rolling(entry).max().shift(1)
    low = frame["low"].rolling(exit).min().shift(1)
    raw = pd.Series(np.nan, index=close.index)
    raw[close > high] = 1.0
    raw[close < low] = 0.0
    position = raw.ffill().fillna(0.0)
    returns = close.pct_change()
    scale = (target_vol / _vol(returns)).clip(upper=3.0).fillna(0.0)
    sized = (position * scale).shift(1).fillna(0.0)
    turnover = sized.diff().abs().fillna(0.0)
    pnl = sized * returns - turnover * cost_bps / 10_000
    return pnl.fillna(0.0)


def breakout(frame: pd.DataFrame, *, entry: int = 20, exit: int = 10,
             target_vol: float = 0.40, cost_bps: float = 6.0) -> list[float]:
    return breakout_series(
        frame, entry=entry, exit=exit, target_vol=target_vol, cost_bps=cost_bps
    ).tolist()


def xsmom(frames: dict[str, pd.DataFrame], *, lookback: int = 30, top_k: int = 3,
          rebalance: int = 7, cost_bps: float = 6.0) -> tuple[list[float], list[str]]:
    """Kesitsel momentum: her rebalance gunu en iyi k long, en kotu k short (esit agir)."""
    closes = pd.DataFrame({coin: frame["close"] for coin, frame in frames.items()}).dropna(how="all")
    returns = closes.pct_change()
    momentum = closes / closes.shift(lookback) - 1
    dates = closes.index
    position = pd.DataFrame(0.0, index=dates, columns=closes.columns)
    members: list[str] = []
    for index in range(len(dates)):
        if index % rebalance != 0 or index < lookback + 1:
            continue
        row = momentum.iloc[index].dropna()
        if len(row) < top_k * 2:
            continue
        ordered = row.sort_values()
        shorts = list(ordered.index[:top_k])
        longs = list(ordered.index[-top_k:])
        position.iloc[index:] = 0.0
        position.loc[dates[index]:, longs] = 0.5 / top_k
        position.loc[dates[index]:, shorts] = -0.5 / top_k
        members.append(dates[index].date().isoformat())
    sized = position.shift(1).fillna(0.0)
    turnover = sized.diff().abs().sum(axis=1).fillna(0.0)
    gross = (sized * returns).sum(axis=1)
    net = gross - turnover * cost_bps / 10_000
    return net.fillna(0.0).tolist(), members


def carry_series(funding_daily: dict[str, float], *, cost_bps: float = 6.0,
                 horizon_days: int = 30) -> pd.Series:
    """Delta-notr fonlama tasiyiciligi: long spot + short perp.

    Kisa perp bacagi pozitif fonlamayi **alir** (long'lar oder). Gunluk getiri
    +fonlama; maliyet her horizon_days basinda iki bacak icin dusulur.
    """
    if not funding_daily:
        return pd.Series(dtype=float)
    index = pd.to_datetime(sorted(funding_daily), utc=True)
    values = []
    for position, day in enumerate(sorted(funding_daily)):
        rate = funding_daily[day]
        cost = cost_bps / 10_000 * 2 if position % horizon_days == 0 else 0.0
        values.append(rate - cost)
    return pd.Series(values, index=index)


def carry(funding_daily: dict[str, float], *, cost_bps: float = 6.0,
          horizon_days: int = 30) -> list[float]:
    return carry_series(funding_daily, cost_bps=cost_bps, horizon_days=horizon_days).tolist()


def carry_frame(funding: dict[str, dict[str, float]]) -> pd.DataFrame:
    """Coin bazli gunluk fonlama toplamlari (satirlar gun, kolonlar coin)."""
    frame = pd.DataFrame({coin: pd.Series(series) for coin, series in funding.items()})
    frame.index = pd.to_datetime(frame.index, utc=True)
    return frame.sort_index().astype(float)


def carry_xs(
    funding: dict[str, dict[str, float]],
    *, top_n: int = 4, rebalance: int = 7, lookback: int = 7,
    cost_bps: float = 6.0, min_avg: float = 0.0,
    target_vol: float | None = 0.10, max_leverage: float = 3.0,
) -> pd.Series:
    """Kesitsel fonlama carry: her hafta fonlamasi en yuksek N coinde long spot + short perp.

    Sadece geriye donuk `lookback` gun ortalamasi `min_avg` ustundeki coinler secilir
    (negatif fonlama rejiminde pozisyon acilmaz). Istege bagli portfoy vol hedefleme.
    """
    frame = carry_frame(funding).fillna(0.0)
    dates = frame.index
    position = pd.DataFrame(0.0, index=dates, columns=frame.columns)
    for index in range(len(dates)):
        if index % rebalance != 0 or index < lookback:
            continue
        history = frame.iloc[max(0, index - lookback + 1): index + 1].mean()
        eligible = history[history > min_avg]
        if eligible.empty:
            continue
        chosen = eligible.sort_values(ascending=False).head(top_n).index
        position.iloc[index:] = 0.0
        position.loc[dates[index]:, chosen] = 1.0 / len(chosen)
    held = position.shift(1).fillna(0.0)
    turnover = position.diff().abs().sum(axis=1).fillna(0.0)
    gross = (held * frame).sum(axis=1)
    net = gross - turnover * cost_bps * 2 / 10_000
    if target_vol:
        realized = net.rolling(30).std() * math.sqrt(TRADING_DAYS)
        leverage = (target_vol / realized).clip(upper=max_leverage).shift(1).fillna(0.0)
        net = net * leverage
    return net.fillna(0.0)


def _portfolio(series_map: dict[str, pd.Series]) -> pd.Series:
    frame = pd.DataFrame(series_map)
    available = frame.notna().sum(axis=1)
    return (frame.mean(axis=1) * len(series_map) / available.replace(0, np.nan)).fillna(0.0)


def scan(
    frames: dict[str, pd.DataFrame],
    funding: dict[str, dict[str, float]] | None = None,
    *, cost_bps: float = 6.0,
) -> list[dict[str, Any]]:
    """Tum aileleri kucuk bir parametre izgarasinda tarar ve metrik tablosu dondurur."""
    results: list[dict[str, Any]] = []
    btc = frames.get("bitcoin")
    btc_returns = btc["close"].pct_change().fillna(0.0).tolist() if btc is not None else None

    def add(family: str, params: str, series: pd.Series | list[float]) -> None:
        daily = series.tolist() if isinstance(series, pd.Series) else series
        stats = metrics(daily, btc_returns if family != "CARRY" else None)
        results.append({"family": family, "params": params, **stats})

    for lookback in (7, 30, 90):
        for coin, frame in frames.items():
            add("TSMOM", f"{coin} lb={lookback}", tsmom_series(frame, lookback=lookback, cost_bps=cost_bps))

    for lookback in (7, 30, 90):
        for rebalance in (7, 30):
            daily, _ = xsmom(frames, lookback=lookback, top_k=3, rebalance=rebalance, cost_bps=cost_bps)
            add("XSMOM", f"lb={lookback} rb={rebalance} k=3", daily)

    for coin, frame in frames.items():
        add("BREAK", f"{coin} 20/10", breakout_series(frame, cost_bps=cost_bps))

    carry_map: dict[str, pd.Series] = {}
    if funding:
        for coin, series in funding.items():
            carried = carry_series(series, cost_bps=cost_bps)
            carry_map[coin] = carried
            add("CARRY", f"{coin} delta-notr", carried)

    break_map = {
        coin: breakout_series(frame, cost_bps=cost_bps) for coin, frame in frames.items()
    }
    if break_map:
        add("PORTFOY", "BREAK esit agir (10 coin)", _portfolio(break_map))
    if carry_map:
        add("PORTFOY", "CARRY esit agir (10 coin)", _portfolio(carry_map))
    if break_map and carry_map:
        mixed = _portfolio(
            {
                **{f"b_{coin}": series for coin, series in break_map.items()},
                **{f"c_{coin}": series for coin, series in carry_map.items()},
            }
        )
        add("PORTFOY", "BREAK+CARRY esit agir", mixed)
    if break_map:
        vol_targeted = _portfolio(
            {coin: series / (series.rolling(30).std() * math.sqrt(365)).replace(0, np.nan)
             for coin, series in break_map.items()}
        ).clip(-0.05, 0.05)
        add("PORTFOY", "BREAK vol-hedefli", vol_targeted)
    return results
