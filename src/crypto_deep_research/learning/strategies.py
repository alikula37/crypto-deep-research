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


def pit_mask_from_volumes(
    volume_frame: pd.DataFrame, *, top: int = 40, lookback: int = 30
) -> pd.DataFrame:
    """Nokta-zamaninda evren maskesi: trailing ortalama dolar hacmine gore ilk `top` coin."""
    trailing = volume_frame.rolling(lookback, min_periods=max(5, lookback // 3)).mean()
    mask = pd.DataFrame(False, index=volume_frame.index, columns=volume_frame.columns)
    for day in volume_frame.index:
        row = trailing.loc[day].dropna().sort_values(ascending=False).head(top)
        mask.loc[day, row.index] = True
    return mask


async def build_pit_funding(
    providers, *, days: int = 1500, top: int = 40, candidates: int = 60
) -> tuple[dict[str, dict[str, float]], float]:
    """Nokta-zamaninda evrenle maskelenmis fonlama haritasi (survivorship bias kontrolu).

    Aday evrenden (en likit `candidates` perp) her gun trailing 30g dolar hacmine gore ilk
    `top` coin secilir; bu evrenin disindaki fonlamalar NaN'a cevrilir. Donen ikinci deger
    maske kapsama oranidir (hucre yuzdesi).
    """
    symbols = await providers.exchange.perp_universe(top=candidates, min_volume_usd=5_000_000)
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    start_ms = now_ms - days * DAY_MS
    funding: dict[str, dict[str, float]] = {}
    volumes: dict[str, dict[str, float]] = {}
    for symbol in symbols:
        rows = await providers.exchange.funding_history(symbol, days=days)
        daily: dict[str, list[float]] = {}
        for timestamp, rate in rows:
            day = datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc).date().isoformat()
            daily.setdefault(day, []).append(rate)
        if daily:
            funding[symbol] = {day: sum(values) for day, values in daily.items()}
        klines = await providers.exchange.perp_klines_range(
            symbol, "1d", start_ms=start_ms, end_ms=now_ms
        )
        if klines:
            volumes[symbol] = {k.ts.date().isoformat(): k.volume * k.close for k in klines}

    frame = carry_frame(funding)
    volume_frame = pd.DataFrame(volumes).sort_index()
    volume_frame.index = pd.to_datetime(volume_frame.index, utc=True)
    volume_frame = volume_frame[~volume_frame.index.duplicated(keep="last")]
    common = frame.index.intersection(volume_frame.index)
    frame = frame.loc[common]
    volume_frame = volume_frame.loc[common]
    mask = pit_mask_from_volumes(volume_frame, top=top, lookback=30)
    masked = frame.where(mask)
    coverage = float(mask.values.mean())
    masked_funding = {
        str(column): {
            day.isoformat(): float(value)
            for day, value in masked[column].dropna().items()
        }
        for column in masked.columns
    }
    return masked_funding, coverage


def select_holdings(
    history: dict[str, float],
    *,
    top_n: int = 8,
    min_avg: float = 0.0,
    max_avg: float | None = None,
    incumbents: set[str] | None = None,
    hysteresis: float = 0.0,
    weighting: str = "equal",
    max_weight: float = 0.25,
) -> dict[str, float]:
    """Fonlama gecmisinden pozisyon secimi ve agirliklandirma.

    - `hysteresis`: mevcut pozisyonlara siralamada eklenen fonlama avantaji; gereksiz
      turnover'i azaltir (ornek: 0.0002 = gunluk 2 bps).
    - `weighting`: "equal" esit agirlik, "funding" fonlama ile orantili (ust sinirli).
    """
    incumbents = incumbents or set()
    candidates = [
        (symbol, float(value))
        for symbol, value in history.items()
        if value is not None and value == value and value > min_avg
    ]
    if max_avg is not None:
        candidates = [(symbol, value) for symbol, value in candidates if value <= max_avg]
    if not candidates:
        return {}
    candidates.sort(
        key=lambda item: item[1] + (hysteresis if item[0] in incumbents else 0.0),
        reverse=True,
    )
    chosen = candidates[:top_n]
    if weighting == "funding":
        positive = {symbol: value for symbol, value in chosen if value > 0}
        if not positive:
            return {symbol: 1 / len(chosen) for symbol, _ in chosen}
        total = sum(positive.values())
        weights = {symbol: value / total for symbol, value in positive.items()}
        for _ in range(5):
            over = {symbol for symbol, weight in weights.items() if weight > max_weight}
            if not over:
                break
            excess = sum(weights[symbol] - max_weight for symbol in over)
            for symbol in over:
                weights[symbol] = max_weight
            free = [symbol for symbol in weights if symbol not in over]
            base = sum(weights[symbol] for symbol in free)
            if base <= 0 or not free:
                break
            for symbol in free:
                weights[symbol] += excess * weights[symbol] / base
        return weights
    return {symbol: 1 / len(chosen) for symbol, _ in chosen}


def carry_xs(
    funding: dict[str, dict[str, float]],
    *, top_n: int = 4, rebalance: int = 7, lookback: int = 7,
    cost_bps: float = 6.0, min_avg: float = 0.0, max_avg: float | None = None,
    weighting: str = "equal", hysteresis: float = 0.0, max_weight: float = 0.25,
    target_vol: float | None = None, max_leverage: float = 3.0,
) -> pd.Series:
    """Kesitsel fonlama carry: her hafta fonlamasi en yuksek N coinde long spot + short perp.

    Sadece geriye donuk `lookback` gun ortalamasi `min_avg` ustundeki coinler secilir
    (negatif fonlama rejiminde pozisyon acilmaz). Istege bagli portfoy vol hedefleme.
    """
    frame = carry_frame(funding).fillna(0.0)
    dates = frame.index
    position = pd.DataFrame(0.0, index=dates, columns=frame.columns)
    current: set[str] = set()
    for index in range(len(dates)):
        if index % rebalance != 0 or index < lookback:
            continue
        history = frame.iloc[max(0, index - lookback + 1): index + 1].mean().to_dict()
        weights = select_holdings(
            history,
            top_n=top_n,
            min_avg=min_avg,
            max_avg=max_avg,
            incumbents=current,
            hysteresis=hysteresis,
            weighting=weighting,
            max_weight=max_weight,
        )
        if not weights:
            continue
        position.iloc[index:] = 0.0
        for symbol, weight in weights.items():
            position.loc[dates[index]:, symbol] = weight
        current = set(weights)
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
