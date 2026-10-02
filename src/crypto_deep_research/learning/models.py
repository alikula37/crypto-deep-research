"""Saf NumPy modeller: standardizasyon, L2 lojistik, Platt ve izotonik kalibrasyon.

Dis bagimlilik (sklearn vb.) eklemeden calisir; boyutlar kucuk oldugu icin
gradyan inişi ile egitim yeterlidir.
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any

import numpy as np

EVALUATION_PROTOCOL = "separate_calibration_final_holdout_v1"


def _sigmoid(values: np.ndarray) -> np.ndarray:
    clipped = np.clip(values, -30.0, 30.0)
    return 1.0 / (1.0 + np.exp(-clipped))


def logit(probability: float) -> float:
    clipped = min(max(probability, 1e-6), 1 - 1e-6)
    return math.log(clipped / (1 - clipped))


class Standardizer:
    def fit(self, X: Any) -> Standardizer:
        array = np.asarray(X, dtype=float)
        self.mean = array.mean(axis=0)
        self.std = array.std(axis=0)
        self.std[self.std < 1e-9] = 1.0
        return self

    def transform(self, X: Any) -> np.ndarray:
        return (np.asarray(X, dtype=float) - self.mean) / self.std

    def to_params(self) -> dict[str, list[float]]:
        return {"mean": self.mean.tolist(), "std": self.std.tolist()}

    @classmethod
    def from_params(cls, params: dict[str, Any]) -> Standardizer:
        scaler = cls()
        scaler.mean = np.asarray(params["mean"], dtype=float)
        scaler.std = np.asarray(params["std"], dtype=float)
        return scaler


class LogisticModel:
    """L2 duzenlilestirilmis lojistik regresyon (gradyan inişi)."""

    def __init__(self, l2: float = 1.0, iterations: int = 1200, learning_rate: float = 0.2) -> None:
        self.l2 = l2
        self.iterations = iterations
        self.learning_rate = learning_rate

    def fit(self, X: Any, y: Any) -> LogisticModel:
        self.scaler = Standardizer().fit(X)
        Z = self.scaler.transform(X)
        labels = np.asarray(y, dtype=float)
        n, dim = Z.shape
        weights = np.zeros(dim)
        intercept = 0.0
        for _ in range(self.iterations):
            probabilities = _sigmoid(Z @ weights + intercept)
            gradient_w = (Z.T @ (probabilities - labels)) / n + self.l2 * weights / n
            gradient_b = float(np.mean(probabilities - labels))
            weights -= self.learning_rate * gradient_w
            intercept -= self.learning_rate * gradient_b
        self.weights = weights
        self.intercept = intercept
        return self

    def predict_proba(self, X: Any) -> list[float]:
        Z = self.scaler.transform(X)
        return _sigmoid(Z @ self.weights + self.intercept).tolist()

    def to_params(self) -> dict[str, Any]:
        return {
            "weights": self.weights.tolist(),
            "intercept": float(self.intercept),
            "scaler": self.scaler.to_params(),
        }

    @classmethod
    def from_params(cls, params: dict[str, Any]) -> LogisticModel:
        model = cls()
        model.weights = np.asarray(params["weights"], dtype=float)
        model.intercept = float(params["intercept"])
        model.scaler = Standardizer.from_params(params["scaler"])
        return model


def platt_fit(scores: Any, y: Any, iterations: int = 800, learning_rate: float = 0.05) -> tuple[float, float]:
    """Lojistik skorlari (logit) uzerine a,b kalibrasyon parametrelerini fit eder."""
    values = np.asarray(scores, dtype=float)
    labels = np.asarray(y, dtype=float)
    a, b = 1.0, 0.0
    for _ in range(iterations):
        probabilities = _sigmoid(a * values + b)
        a -= learning_rate * float(np.mean((probabilities - labels) * values))
        b -= learning_rate * float(np.mean(probabilities - labels))
    return a, b


def platt_apply(a: float, b: float, scores: Any) -> list[float]:
    return _sigmoid(a * np.asarray(scores, dtype=float) + b).tolist()


def isotonic_fit(scores: Any, y: Any) -> list[tuple[float, float]]:
    """PAVA ile monoton azalmayan izotonik kalibrasyon eslemesi uretir."""
    values = np.asarray(scores, dtype=float)
    labels = np.asarray(y, dtype=float)
    order = np.argsort(values)
    xs = values[order]
    ys = labels[order]
    blocks: list[list[float]] = []  # [sum, weight]
    for value in ys:
        blocks.append([float(value), 1.0])
        while len(blocks) >= 2 and blocks[-2][0] / blocks[-2][1] > blocks[-1][0] / blocks[-1][1]:
            merged_sum = blocks[-2][0] + blocks[-1][0]
            merged_weight = blocks[-2][1] + blocks[-1][1]
            blocks.pop()
            blocks.pop()
            blocks.append([merged_sum, merged_weight])
    points: list[tuple[float, float]] = []
    index = 0
    for total, weight in blocks:
        count = int(weight)
        x_avg = float(np.mean(xs[index : index + count]))
        points.append((x_avg, total / weight))
        index += count
    return points


def isotonic_apply(points: list[tuple[float, float]], scores: Any) -> list[float]:
    if not points:
        return []
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return np.interp(np.asarray(scores, dtype=float), xs, ys).tolist()


def auc_score(y: Any, probabilities: Any) -> float | None:
    labels = np.asarray(y, dtype=float)
    scores = np.asarray(probabilities, dtype=float)
    positives = labels.sum()
    negatives = len(labels) - positives
    if positives == 0 or negatives == 0:
        return None
    order = np.argsort(scores)
    ranks = np.empty(len(scores))
    ranks[order] = np.arange(1, len(scores) + 1)
    rank_sum = float(np.sum(ranks[labels == 1]))
    return round((rank_sum - positives * (positives + 1) / 2) / (positives * negatives), 4)


def brier_score(y: Any, probabilities: Any) -> float | None:
    labels = np.asarray(y, dtype=float)
    scores = np.asarray(probabilities, dtype=float)
    if len(labels) == 0:
        return None
    return round(float(np.mean((scores - labels) ** 2)), 4)


def log_loss_score(y: Any, probabilities: Any) -> float | None:
    labels = np.asarray(y, dtype=float)
    scores = np.clip(np.asarray(probabilities, dtype=float), 1e-6, 1 - 1e-6)
    if len(labels) == 0:
        return None
    return round(float(-np.mean(labels * np.log(scores) + (1 - labels) * np.log(1 - scores))), 4)


def expected_calibration_error(y: Any, probabilities: Any, bins: int = 10) -> float | None:
    labels = np.asarray(y, dtype=float)
    scores = np.asarray(probabilities, dtype=float)
    if len(labels) == 0:
        return None
    total = 0.0
    for index in range(bins):
        low = index / bins
        high = (index + 1) / bins
        mask = (scores >= low) & (scores < high if index < bins - 1 else scores <= high)
        count = int(mask.sum())
        if count == 0:
            continue
        total += (count / len(labels)) * abs(float(scores[mask].mean()) - float(labels[mask].mean()))
    return round(total, 4)


def probability_bins(y: Any, probabilities: Any, bins: int = 10) -> list[dict[str, Any]]:
    labels = np.asarray(y, dtype=float)
    scores = np.asarray(probabilities, dtype=float)
    result: list[dict[str, Any]] = []
    for index in range(bins):
        low = index / bins
        high = (index + 1) / bins
        mask = (scores >= low) & (scores < high if index < bins - 1 else scores <= high)
        count = int(mask.sum())
        if count == 0:
            continue
        hits = int(labels[mask].sum())
        result.append(
            {
                "bin_index": index,
                "bin_low": round(low, 3),
                "bin_high": round(high, 3),
                "n": count,
                "predicted_mean": round(float(scores[mask].mean()), 4),
                "observed_rate": round(hits / count, 4),
                "hits": hits,
            }
        )
    return result


def purged_walk_forward(
    dates: list[str],
    *,
    horizon_days: int,
    folds: int = 4,
    min_train: int = 10,
) -> list[tuple[list[int], list[int]]]:
    """Tarihler bazinda gruplu, purge'lu ileri yuruyuslu CV pencereleri uretir.

    Ayni tarihteki ornekler ayni fold'da kalir. Her etiketin ileri ufuk penceresi
    sonraki test araligi ile ortusebileceginden, yeterince eski olmayan egitim
    ornekleri purge edilir.
    """
    parsed: list[date | None] = []
    for value in dates:
        try:
            parsed.append(date.fromisoformat(value))
        except (TypeError, ValueError):
            parsed.append(None)
    unique_dates = sorted({value for value in parsed if value is not None})
    if len(unique_dates) < folds + 1:
        return []
    fold_size = max(1, len(unique_dates) // (folds + 1))
    windows: list[tuple[list[int], list[int]]] = []
    for fold in range(1, folds + 1):
        test_start = fold * fold_size
        test_end = min(len(unique_dates), test_start + fold_size) if fold < folds else len(unique_dates)
        if test_start >= len(unique_dates) or test_end <= test_start:
            continue
        test_start_date = unique_dates[test_start]
        test_dates = set(unique_dates[test_start:test_end])
        train_indices: list[int] = []
        test_indices: list[int] = []
        for index, sample_date in enumerate(parsed):
            if sample_date in test_dates:
                test_indices.append(index)
                continue
            if sample_date is None or sample_date >= test_start_date:
                continue
            if sample_date + timedelta(days=horizon_days) < test_start_date:
                train_indices.append(index)
        if len(train_indices) < min_train:
            continue
        if test_indices:
            windows.append((train_indices, test_indices))
    return windows


def economic_metrics(
    probabilities: Any,
    returns_pct: Any,
    *,
    horizon_days: int = 1,
    cost_bps: float = 10.0,
    scale: float = 2.0,
) -> dict[str, Any]:
    """Olasiliklardan basit pozisyon stratejisi turetir; maliyet sonrasi Sharpe hesaplar.

    Pozisyon = clip((p - 0.5) x scale, -1, 1); her degisimde cost_bps maliyet duser.
    Yilliklandirma sqrt(252 / horizon_days) ile yapilir.
    """
    positions: list[float] = []
    gross: list[float] = []
    net: list[float] = []
    previous = 0.0
    for probability, value in zip(probabilities, returns_pct, strict=False):
        position = max(-1.0, min(1.0, (float(probability) - 0.5) * scale))
        turnover = abs(position - previous)
        gross_pnl = position * (float(value) / 100.0)
        net_pnl = gross_pnl - turnover * cost_bps / 10_000
        positions.append(position)
        gross.append(gross_pnl)
        net.append(net_pnl)
        previous = position
    if not net:
        return {}

    def _sharpe(values: list[float]) -> float | None:
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / max(len(values) - 1, 1)
        deviation = variance ** 0.5
        if deviation <= 0:
            return None
        factor = (252.0 / max(horizon_days, 1)) ** 0.5
        return round(mean / deviation * factor, 3)

    return {
        "net_sharpe": _sharpe(net),
        "gross_sharpe": _sharpe(gross),
        "avg_abs_position": round(sum(abs(p) for p in positions) / len(positions), 3),
        "active_ratio": round(sum(1 for p in positions if abs(p) > 0.2) / len(positions), 3),
    }
