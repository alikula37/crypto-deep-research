"""Egitim veri seti: ozellik vektorleri + etiketler (saf Python, dis bagimlilik yok)."""

from __future__ import annotations

import json
import math
from typing import Any

from crypto_deep_research.learning.history import EXTENDED_FEATURE_NAMES, EXTENDED_ITEM_IDS

FEATURE_NAMES = [
    "weighted_score",
    "signal_strength",
    "coverage_ratio",
    "coverage_weighted",
    "score_dispersion",
    "confidence_mean",
    "atr_pct_log",
    "no_data_ratio",
    "partial_ratio",
    "category_spread",
]

EXTENDED_ORDER = list(EXTENDED_ITEM_IDS.values())
FULL_FEATURE_NAMES = FEATURE_NAMES + EXTENDED_FEATURE_NAMES + ["x_present_ratio"]


def _category_spread(raw: Any) -> float:
    if not raw:
        return 0.0
    try:
        values = list(json.loads(raw).values())
    except (ValueError, TypeError):
        return 0.0
    if len(values) < 2:
        return 0.0
    return float(max(values) - min(values))


def row_features(row: dict[str, Any]) -> dict[str, float]:
    """feature_snapshots satirindan sabit ozellik vektoru uretir."""
    total = max(
        (row.get("n_ok") or 0)
        + (row.get("n_partial") or 0)
        + (row.get("n_no_data") or 0)
        + (row.get("n_error") or 0),
        1,
    )
    atr = row.get("atr_pct")
    return {
        "weighted_score": float(row.get("weighted_score") or 0.0),
        "signal_strength": float(row.get("signal_strength") or 0.0),
        "coverage_ratio": float(row.get("coverage_ratio") or 0.0),
        "coverage_weighted": float(row.get("coverage_weighted") or 0.0),
        "score_dispersion": float(row.get("score_dispersion") or 0.0),
        "confidence_mean": float(row.get("confidence_mean") or 0.0),
        "atr_pct_log": math.log1p(float(atr)) if atr else 0.0,
        "no_data_ratio": round((row.get("n_no_data") or 0) / total, 4),
        "partial_ratio": round((row.get("n_partial") or 0) / total, 4),
        "category_spread": round(_category_spread(row.get("category_scores")), 4),
    }


def vector_for(
    snapshot: dict[str, Any], extended: dict[int, float] | None = None
) -> list[float]:
    """Tek bir anlik goruntu icin tam ozellik vektorunu uretir (25 boyut)."""
    base = row_features(snapshot)
    values = [base[name] for name in FEATURE_NAMES]
    ext = extended or {}
    present = 0
    for item_id in EXTENDED_ORDER:
        value = ext.get(item_id)
        if value is None:
            values.append(0.0)
        else:
            values.append(float(value))
            present += 1
    values.append(round(present / max(len(EXTENDED_ORDER), 1), 4))
    return values


def build_dataset(
    rows: list[dict[str, Any]],
    extended: dict[str, dict[int, float]] | None = None,
) -> dict[str, Any]:
    """Etiketli satirlari X/y/dates/coins yapisina cevirir (tarihe gore sirali)."""
    extended = extended or {}
    features, labels, dates, coins, run_ids, returns = [], [], [], [], [], []
    for row in rows:
        features.append(vector_for(row, extended.get(str(row.get("run_id") or ""), {})))
        labels.append(1 if (row.get("return_pct") or 0) > 0 else 0)
        returns.append(float(row.get("return_pct") or 0.0))
        dates.append(str(row.get("target_date") or ""))
        coins.append(str(row.get("coin") or ""))
        run_ids.append(str(row.get("run_id") or ""))
    return {
        "X": features,
        "y": labels,
        "returns": returns,
        "dates": dates,
        "coins": coins,
        "run_ids": run_ids,
        "feature_names": list(FULL_FEATURE_NAMES),
    }
