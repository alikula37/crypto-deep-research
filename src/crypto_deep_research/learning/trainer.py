"""Model egitimi: purged walk-forward degerlendirme, kalibrasyon ve kayit."""

from __future__ import annotations

import logging
import time
from typing import Any

from crypto_deep_research.learning.dataset import build_dataset, row_features
from crypto_deep_research.learning.models import (
    LogisticModel,
    auc_score,
    brier_score,
    expected_calibration_error,
    log_loss_score,
    logit,
    platt_apply,
    platt_fit,
    probability_bins,
    purged_walk_forward,
)

logger = logging.getLogger(__name__)

MIN_SAMPLES = 30
ACTIVATE_MIN_SAMPLES = 200
ACTIVATE_MIN_AUC = 0.55


def _status_gate(metrics: dict[str, Any], n: int, activate_min: int) -> str:
    if (
        n >= activate_min
        and metrics.get("auc") is not None
        and metrics["auc"] >= ACTIVATE_MIN_AUC
        and metrics.get("brier") is not None
        and metrics.get("baseline_brier") is not None
        and metrics["brier"] < metrics["baseline_brier"]
    ):
        return "active"
    return "shadow"


def predict_snapshot(snapshot: dict[str, Any], params: dict[str, Any]) -> float:
    """Kayitli model parametreleriyle tek anlik goruntu icin olasilik uretir."""
    vector = [row_features(snapshot)[name] for name in params.get("feature_names") or []]
    if not vector:
        vector = list(row_features(snapshot).values())
    model = LogisticModel.from_params(params["logistic"])
    raw = model.predict_proba([vector])[0]
    calibration = params.get("calibration")
    if calibration:
        return platt_apply(calibration["platt_a"], calibration["platt_b"], [logit(raw)])[0]
    return raw


def _write_predictions(
    db,
    horizon: int,
    model_id: str,
    params: dict[str, Any],
    status: str,
    n_train: int,
) -> int:
    """Tum kosular icin shadow/aktif model tahmini yazar (gecmis karsilastirmasi icin)."""
    written = 0
    snapshots = db.query(
        "SELECT * FROM feature_snapshots ORDER BY created_at DESC LIMIT 2000"
    )
    for snapshot in snapshots:
        try:
            probability = predict_snapshot(snapshot, params)
        except Exception:
            logger.warning("Tahmin uretilemedi: %s", snapshot.get("run_id"))
            continue
        db.prediction_save(
            {
                "run_id": snapshot["run_id"],
                "horizon_days": horizon,
                "model_id": model_id,
                "heuristic_up": snapshot.get("up_probability"),
                "probability_up": round(probability * 100, 2),
                "probability_down": round((1 - probability) * 100, 2),
                "n_train": n_train,
                "is_shadow": status != "active",
            }
        )
        written += 1
    return written


def train_horizon(
    db,
    horizon: int = 7,
    *,
    min_samples: int = MIN_SAMPLES,
    activate_min: int = ACTIVATE_MIN_SAMPLES,
    coin: str | None = None,
) -> dict[str, Any]:
    """Tek ufuk icin model egitir; yetersiz veride egitim yapmaz."""
    rows = db.learning_rows(horizon, coin=coin)
    dataset = build_dataset(rows)
    n = len(dataset["y"])
    if n < min_samples:
        return {
            "status": "insufficient",
            "horizon_days": horizon,
            "n": n,
            "min_samples": min_samples,
        }

    windows = purged_walk_forward(
        dataset["dates"], horizon_days=horizon, folds=4, min_train=max(8, min_samples // 3)
    )
    oos_probability: list[float] = []
    oos_labels: list[int] = []
    for train_idx, test_idx in windows:
        model = LogisticModel(l2=1.0).fit(
            [dataset["X"][index] for index in train_idx],
            [dataset["y"][index] for index in train_idx],
        )
        oos_probability.extend(model.predict_proba([dataset["X"][index] for index in test_idx]))
        oos_labels.extend(dataset["y"][index] for index in test_idx)

    metrics: dict[str, Any] = {"n": n, "n_oos": len(oos_labels), "folds": len(windows)}
    calibration: dict[str, float] | None = None
    bins: list[dict[str, Any]] = []
    if oos_probability:
        logits = [logit(value) for value in oos_probability]
        a, b = platt_fit(logits, oos_labels)
        calibrated = platt_apply(a, b, logits)
        base_rate = sum(oos_labels) / len(oos_labels)
        metrics.update(
            {
                "auc": auc_score(oos_labels, calibrated),
                "brier": brier_score(oos_labels, calibrated),
                "baseline_brier": brier_score(oos_labels, [base_rate] * len(oos_labels)),
                "log_loss": log_loss_score(oos_labels, calibrated),
                "ece": expected_calibration_error(oos_labels, calibrated),
                "base_rate": round(base_rate, 4),
            }
        )
        calibration = {"platt_a": a, "platt_b": b}
        bins = probability_bins(oos_labels, calibrated)

    final = LogisticModel(l2=1.0).fit(dataset["X"], dataset["y"])
    model_id = f"logreg_platt_h{horizon}_{int(time.time())}"
    status = _status_gate(metrics, n, activate_min)
    params = {
        "logistic": final.to_params(),
        "calibration": calibration,
        "feature_names": dataset["feature_names"],
    }
    db.model_save(
        {
            "model_id": model_id,
            "kind": "logreg_platt",
            "horizon_days": horizon,
            "status": status,
            "trained_at": time.time(),
            "train_rows": n,
            "feature_schema_version": 1,
            "params": __import__("json").dumps(params),
            "metrics": __import__("json").dumps(metrics),
            "notes": "Purged walk-forward OOS metrikleri; kalibrasyon Platt (OOS).",
        }
    )
    if bins:
        db.calibration_bins_save(model_id, horizon, bins)
    written = _write_predictions(db, horizon, model_id, params, status, n)
    return {
        "status": "trained",
        "model_id": model_id,
        "horizon_days": horizon,
        "n": n,
        "model_status": status,
        "activated": status == "active",
        "predictions_written": written,
        "metrics": metrics,
    }


def train_all(db, *, min_samples: int = MIN_SAMPLES) -> list[dict[str, Any]]:
    return [train_horizon(db, horizon, min_samples=min_samples) for horizon in (1, 7, 30)]


def latest_model_prediction(db, coin: str, horizon: int = 7) -> dict[str, Any] | None:
    """Aktif/shadow model varsa bu coin icin tahmin uretir."""
    import json

    model = db.model_get(horizon)
    snapshot = db.latest_feature_snapshot(coin)
    if not model or not snapshot:
        return None
    try:
        params = json.loads(model.get("params") or "{}")
        probability = predict_snapshot(snapshot, params)
    except Exception:
        return None
    return {
        "model_id": model["model_id"],
        "kind": model["kind"],
        "status": model["status"],
        "up": round(probability * 100, 2),
        "down": round((1 - probability) * 100, 2),
        "train_rows": model.get("train_rows"),
    }
