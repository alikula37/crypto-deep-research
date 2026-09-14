"""Drift izleme: kapsam, skor dagilimi (PSI) ve kalibrasyon sapmasi."""

from __future__ import annotations

import logging
import math
import time
from typing import Any

from crypto_deep_research.learning.calibration import calibration_table

logger = logging.getLogger(__name__)

DAY = 86_400
COVERAGE_DELTA_WARN = 0.10
PSI_WARN = 0.10
PSI_ALERT = 0.25
ECE_ALERT = 0.10
MIN_SAMPLES_PSI = 10


def population_stability_index(
    baseline: list[float], recent: list[float], bins: int = 10
) -> float | None:
    """Iki dagilim arasindaki PSI degerini hesaplar (0'a yakin = benzer)."""
    if len(baseline) < MIN_SAMPLES_PSI or len(recent) < MIN_SAMPLES_PSI:
        return None
    low = min(min(baseline), min(recent))
    high = max(max(baseline), max(recent))
    if high - low < 1e-9:
        return 0.0
    width = (high - low) / bins
    epsilon = 1e-6
    psi = 0.0
    for index in range(bins):
        bin_low = low + index * width
        bin_high = low + (index + 1) * width
        if index == bins - 1:
            base_count = sum(1 for value in baseline if bin_low <= value <= bin_high)
            recent_count = sum(1 for value in recent if bin_low <= value <= bin_high)
        else:
            base_count = sum(1 for value in baseline if bin_low <= value < bin_high)
            recent_count = sum(1 for value in recent if bin_low <= value < bin_high)
        base_ratio = max(base_count / len(baseline), epsilon)
        recent_ratio = max(recent_count / len(recent), epsilon)
        psi += (recent_ratio - base_ratio) * math.log(recent_ratio / base_ratio)
    return round(psi, 4)


def compute_drift(
    db,
    *,
    now: float | None = None,
    window_days: int = 30,
    baseline_days: int = 90,
) -> list[dict[str, Any]]:
    """Kapsam, skor dagilimi ve kalibrasyon metrikleri icin drift satirlari uretir."""
    now = now or time.time()
    recent_start = now - window_days * DAY
    baseline_start = recent_start - baseline_days * DAY
    entries: list[dict[str, Any]] = []

    recent_n, recent_cov = db.coverage_between(recent_start, now + 1)
    baseline_n, baseline_cov = db.coverage_between(baseline_start, recent_start)
    if recent_cov is not None and baseline_cov is not None:
        delta = recent_cov - baseline_cov
        entries.append(
            {
                "computed_at": now,
                "window_label": f"{window_days}d",
                "metric": "coverage_delta",
                "value": round(recent_cov, 4),
                "baseline": round(baseline_cov, 4),
                "delta": round(delta, 4),
                "n": recent_n + baseline_n,
                "alarm": abs(delta) > COVERAGE_DELTA_WARN,
                "threshold": COVERAGE_DELTA_WARN,
            }
        )

    recent_scores = db.feature_scores_between(recent_start, now + 1)
    baseline_scores = db.feature_scores_between(baseline_start, recent_start)
    psi = population_stability_index(baseline_scores, recent_scores)
    if psi is not None:
        entries.append(
            {
                "computed_at": now,
                "window_label": f"{window_days}d",
                "metric": "score_psi",
                "value": round(sum(recent_scores) / len(recent_scores), 4) if recent_scores else None,
                "baseline": round(sum(baseline_scores) / len(baseline_scores), 4)
                if baseline_scores
                else None,
                "psi": psi,
                "n": len(recent_scores) + len(baseline_scores),
                "alarm": psi >= PSI_ALERT,
                "threshold": PSI_ALERT,
                "details": {"warn_threshold": PSI_WARN},
            }
        )

    rows = db.outcomes_dataset(7)
    table = calibration_table(rows)
    if table.get("n", 0) >= 30 and table.get("ece") is not None:
        entries.append(
            {
                "computed_at": now,
                "window_label": f"{window_days}d",
                "metric": "ece_h7",
                "value": table["ece"],
                "baseline": table.get("baseline_brier"),
                "delta": None,
                "n": table["n"],
                "alarm": table["ece"] > ECE_ALERT,
                "threshold": ECE_ALERT,
                "details": {"brier": table.get("brier"), "auc": table.get("auc")},
            }
        )

    if entries:
        db.drift_save(entries)
    return entries


def drift_summary(entries: list[dict[str, Any]]) -> dict[str, Any]:
    alarms = [entry for entry in entries if entry.get("alarm")]
    return {
        "computed_at": max((entry["computed_at"] for entry in entries), default=None),
        "metrics": [
            {
                "metric": entry["metric"],
                "value": entry.get("value"),
                "baseline": entry.get("baseline"),
                "delta": entry.get("delta"),
                "psi": entry.get("psi"),
                "alarm": bool(entry.get("alarm")),
                "n": entry.get("n"),
            }
            for entry in entries
        ],
        "alarm_count": len(alarms),
        "degraded": len(alarms) > 0,
    }
