"""Kosu ozelliklerini cikarir ve kalici hale getirir (ogrenme dongusu icin).

Her derin arastirma kosusunda 66 maddenin skor/guyen/durum izleri, kategori
kompozitleri, kapsam ve sinyal gucu SQLite'a yazilir; boylece gunluk veri
biriktikce kalibrasyon ve ML katmani egitilebilir.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)

HORIZONS: tuple[int, ...] = (1, 7, 30)
DIRECTIONAL_THRESHOLD = 0.05
FEATURE_SCHEMA_VERSION = 1


def _items_hash(items) -> str:
    payload = "|".join(
        f"{item.item_id}:{item.status}:{item.score if item.score is not None else 'na'}"
        for item in items
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _direction(weighted_score: float | None) -> str:
    if weighted_score is None:
        return "neutral"
    if weighted_score >= DIRECTIONAL_THRESHOLD:
        return "up"
    if weighted_score <= -DIRECTIONAL_THRESHOLD:
        return "down"
    return "neutral"


def extract_run(
    run,
    specs,
    *,
    group_factors: dict[int, float] | None = None,
    multipliers: dict[int, float] | None = None,
    analysis_results: list | None = None,
) -> dict[str, Any]:
    """Kosu duzeyi ozellik satirini uretir."""
    group_factors = group_factors or {}
    multipliers = multipliers or {}
    items = run.items
    status_counts = {"ok": 0, "partial": 0, "no_data": 0, "error": 0}
    for item in items:
        status_counts[item.status] = status_counts.get(item.status, 0) + 1

    weighted: list[tuple[Any, float]] = []
    contributions: dict[int, float] = {}
    for item in items:
        if item.score is None or item.confidence <= 0 or item.status not in ("ok", "partial"):
            continue
        factor = group_factors.get(item.item_id, 1.0) * multipliers.get(item.item_id, 1.0)
        if item.status == "partial":
            factor *= 0.5
        weight = item.weight * item.confidence * factor
        weighted.append((item, weight))
        contributions[item.item_id] = round(item.score * weight, 6)

    total_weight = sum(weight for _, weight in weighted)
    registry_weight = sum(spec.weight for spec in specs) or 1.0
    coverage_ratio = (
        status_counts["ok"] + 0.5 * status_counts["partial"]
    ) / max(len(items), 1)
    scores = [item.score for item, _ in weighted]
    score_mean = sum(scores) / len(scores) if scores else None
    dispersion = None
    if scores and score_mean is not None:
        dispersion = (sum((value - score_mean) ** 2 for value in scores) / len(scores)) ** 0.5
    confidence_mean = (
        sum(item.confidence for item, _ in weighted) / len(weighted) if weighted else None
    )

    category_scores: dict[str, float] = {}
    category_weight: dict[str, float] = {}
    for item, weight in weighted:
        category_scores[item.category] = category_scores.get(item.category, 0.0) + item.score * weight
        category_weight[item.category] = category_weight.get(item.category, 0.0) + weight
    category_scores = {
        key: round(value / category_weight[key], 4)
        for key, value in category_scores.items()
        if category_weight.get(key)
    }

    strong = [(item, weight) for item, weight in weighted if abs(item.score) >= DIRECTIONAL_THRESHOLD]
    strong_weight = sum(weight for _, weight in strong)
    signal_strength = (
        round(sum(item.score * weight for item, weight in strong) / strong_weight, 4)
        if strong_weight
        else 0.0
    )

    atr_pct = None
    for result in analysis_results or []:
        if getattr(result, "key", None) == "technical":
            atr_pct = ((result.data or {}).get("indicators") or {}).get("atr_pct")

    item_map = {item.item_id: item for item in items}
    regime = None
    fractal = item_map.get(21)
    if fractal is not None and fractal.data:
        regime = fractal.data.get("regime")
    volatility_bucket = None
    vol_item = item_map.get(35)
    if vol_item is not None and vol_item.data:
        percentile = vol_item.data.get("volatility_percentile")
        if percentile is not None:
            volatility_bucket = "low" if percentile < 0.33 else ("high" if percentile > 0.66 else "mid")

    return {
        "run_id": run.run_id,
        "coin": run.coin.id,
        "created_at": run.created_at.timestamp(),
        "profile": getattr(run, "profile", "balanced"),
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "n_ok": status_counts["ok"],
        "n_partial": status_counts["partial"],
        "n_no_data": status_counts["no_data"],
        "n_error": status_counts["error"],
        "coverage_ratio": round(coverage_ratio, 4),
        "coverage_weighted": round(total_weight / registry_weight, 4) if registry_weight else None,
        "weighted_score": run.weighted_score,
        "signal_strength": signal_strength,
        "score_mean": round(score_mean, 4) if score_mean is not None else None,
        "score_dispersion": round(dispersion, 4) if dispersion is not None else None,
        "confidence_mean": round(confidence_mean, 4) if confidence_mean is not None else None,
        "category_scores": json.dumps(category_scores, ensure_ascii=False),
        "atr_pct": atr_pct,
        "regime": regime,
        "volatility_bucket": volatility_bucket,
        "current_price": run.current_price,
        "up_probability": run.up_probability,
        "down_probability": run.down_probability,
        "expected_low": run.expected_low,
        "expected_high": run.expected_high,
        "items_hash": _items_hash(items),
        "contributions": contributions,
    }


def extract_items(
    run,
    *,
    group_factors: dict[int, float] | None = None,
    multipliers: dict[int, float] | None = None,
) -> list[dict[str, Any]]:
    """Madde duzeyi iz satirlarini uretir (66 satir)."""
    group_factors = group_factors or {}
    multipliers = multipliers or {}
    rows: list[dict[str, Any]] = []
    for item in run.items:
        factor = group_factors.get(item.item_id, 1.0) * multipliers.get(item.item_id, 1.0)
        if item.status == "partial":
            factor *= 0.5
        contribution = None
        if item.score is not None and item.confidence > 0:
            contribution = round(item.score * item.weight * item.confidence * factor, 6)
        rows.append(
            {
                "run_id": run.run_id,
                "item_id": item.item_id,
                "coin": run.coin.id,
                "category": item.category,
                "source": getattr(item, "source", None),
                "weight": item.weight,
                "score": item.score,
                "confidence": item.confidence,
                "status": item.status,
                "contribution": contribution,
            }
        )
    return rows


def build_pending_outcomes(run, horizons: tuple[int, ...] = HORIZONS) -> list[dict[str, Any]]:
    """Kosu aninda bekleyen ileri getiri etiketi satirlarini olusturur."""
    created_utc = run.created_at.astimezone(timezone.utc)
    base_date = created_utc.date()
    direction = _direction(run.weighted_score)
    rows: list[dict[str, Any]] = []
    for horizon in horizons:
        target = base_date + timedelta(days=horizon)
        due = datetime(target.year, target.month, target.day, 6, 0, tzinfo=timezone.utc)
        rows.append(
            {
                "run_id": run.run_id,
                "horizon_days": horizon,
                "coin": run.coin.id,
                "symbol": run.coin.symbol.upper(),
                "entry_price": run.current_price,
                "entry_at": run.created_at.timestamp(),
                "target_date": target.isoformat(),
                "due_at": due.timestamp(),
                "direction_at_run": direction,
                "weighted_score": run.weighted_score,
            }
        )
    return rows


def persist_run(
    db,
    run,
    specs,
    *,
    group_factors: dict[int, float] | None = None,
    multipliers: dict[int, float] | None = None,
    analysis_results: list | None = None,
) -> bool:
    """Ozellikleri, madde izlerini ve bekleyen outcome'lari tek transactionda yazar."""
    try:
        if db.query("SELECT 1 FROM feature_snapshots WHERE run_id = ? LIMIT 1", (run.run_id,)):
            return True
        features = extract_run(
            run,
            specs,
            group_factors=group_factors,
            multipliers=multipliers,
            analysis_results=analysis_results,
        )
        contributions = features.pop("contributions", {})
        items = extract_items(run, group_factors=group_factors, multipliers=multipliers)
        for row in items:
            row["contribution"] = contributions.get(row["item_id"], row["contribution"])
        outcomes = build_pending_outcomes(run)
        db.save_learning_run(features, items, outcomes)
        return True
    except Exception:  # ogrenme kaydi kosuyu asla dusurmemeli
        logger.exception("Ogrenme kaydi yazilamadi: %s", run.run_id)
        return False
