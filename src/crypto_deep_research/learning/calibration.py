"""Kalibrasyon: skor kovalarindan gozlenen isabet oranlari + metrikler.

Kalibre edilmis olasilik iddiasi icin gereken kanit katmanidir; yeterli ornek
birikene kadar ciktilar "heuristik" olarak etiketlenir.
"""

from __future__ import annotations

import math
import time
from typing import Any

DIRECTIONAL_THRESHOLD = 0.05
HEURISTIC_SLOPE = 35.0


def heuristic_probability(weighted_score: float | None) -> float:
    if weighted_score is None:
        return 50.0
    value = 50.0 + HEURISTIC_SLOPE * weighted_score
    return max(5.0, min(95.0, value))


def wilson_interval(hits: int, n: int, z: float = 1.96) -> tuple[float | None, float | None]:
    if n <= 0:
        return None, None
    phat = hits / n
    denom = 1 + z * z / n
    center = (phat + z * z / (2 * n)) / denom
    margin = z * math.sqrt((phat * (1 - phat) + z * z / (4 * n)) / n) / denom
    return round(max(0.0, center - margin), 4), round(min(1.0, center + margin), 4)


def brier_score(pairs: list[tuple[float, int]]) -> float | None:
    if not pairs:
        return None
    return round(sum((p - y) ** 2 for p, y in pairs) / len(pairs), 4)


def calibration_table(rows: list[dict[str, Any]], bins: int = 10, prior: float = 2.0) -> dict[str, Any]:
    """(tahmin, gozlem) ciftlerini kovalara ayirir; Beta-binom shrink + Wilson GA."""
    usable: list[tuple[float, int]] = []
    for row in rows:
        hit = row.get("hit")
        score = row.get("f_score", row.get("weighted_score"))
        if hit is None or score is None:
            continue
        usable.append((heuristic_probability(score) / 100.0, int(hit)))

    if not usable:
        return {"n": 0, "bins": [], "brier": None, "baseline_brier": None, "ece": None, "auc": None}

    width = 1.0 / bins
    table: list[dict[str, Any]] = []
    ece = 0.0
    for index in range(bins):
        low = index * width
        high = low + width
        bucket = [(p, y) for p, y in usable if (low <= p < high or (index == bins - 1 and p >= high))]
        if not bucket:
            continue
        n = len(bucket)
        hits = sum(y for _, y in bucket)
        predicted_mean = sum(p for p, _ in bucket) / n
        shrink = (hits + prior) / (n + 2 * prior)
        ci_low, ci_high = wilson_interval(hits, n)
        ece += (n / len(usable)) * abs(shrink - predicted_mean)
        table.append(
            {
                "bin_index": index,
                "bin_low": round(low, 3),
                "bin_high": round(high, 3),
                "n": n,
                "predicted_mean": round(predicted_mean, 4),
                "observed_rate": round(shrink, 4),
                "hits": hits,
                "ci_low": ci_low,
                "ci_high": ci_high,
            }
        )

    positives = sum(y for _, y in usable)
    positives_rate = positives / len(usable)
    baseline = positives_rate * (1 - positives_rate)

    ranked = sorted(usable, key=lambda pair: pair[0])
    positives_total = positives
    negatives_total = len(usable) - positives
    auc = None
    if positives_total and negatives_total:
        rank_sum = 0.0
        for rank, (_p, y) in enumerate(ranked, start=1):
            if y == 1:
                rank_sum += rank
        auc = (rank_sum - positives_total * (positives_total + 1) / 2) / (
            positives_total * negatives_total
        )
        auc = round(auc, 4)

    return {
        "n": len(usable),
        "directional": sum(
            1
            for row in rows
            if row.get("hit") is not None
        ),
        "bins": table,
        "brier": brier_score(usable),
        "baseline_brier": round(baseline, 4),
        "ece": round(ece, 4),
        "auc": auc,
        "computed_at": time.time(),
        "note": (
            "Kalibrasyon icin yeterli ornek yok; degerler heuristiktir."
            if len(usable) < 100
            else "Kalibrasyon kovalari gozleme dayalidir."
        ),
    }
