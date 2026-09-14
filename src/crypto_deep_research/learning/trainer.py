"""Model egitimi: purged walk-forward, kalibrasyon, algoritma secimi ve kayit.

Iki algoritma yarisa girer (n yeterliyse): L2 lojistik ve gradyan artirma.
Secim OOS Brier'e gore yapilir (esitlikte basit model tercih edilir); kalibrasyon
n_oos>=300 ise izotonik, degilse Platt.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from crypto_deep_research.learning.boosting import BoostedTrees
from crypto_deep_research.learning.dataset import (
    FULL_FEATURE_NAMES,
    build_dataset,
    select_features,
    vector_for,
)
from crypto_deep_research.learning.models import (
    LogisticModel,
    auc_score,
    brier_score,
    economic_metrics,
    expected_calibration_error,
    isotonic_apply,
    isotonic_fit,
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
ACTIVATE_MIN_SHARPE = 0.3
BOOST_MIN_SAMPLES = 1500
# Ablasyon (7g, backfill): taban ozellikler en iyi AUC'yi verdi; makro/kesitsel
# ekler bu orneklemde siralama kalitesini dusuruyor -> varsayilan taban.
DEFAULT_FEATURE_GROUPS = ["base"]
ISOTONIC_MIN_SAMPLES = 300
BOOST_BRIER_MARGIN = 0.0005


def _status_gate(metrics: dict[str, Any], n: int, activate_min: int) -> str:
    if (
        n >= activate_min
        and metrics.get("auc") is not None
        and metrics["auc"] >= ACTIVATE_MIN_AUC
        and metrics.get("brier") is not None
        and metrics.get("baseline_brier") is not None
        and metrics["brier"] < metrics["baseline_brier"]
    ):
        net_sharpe = metrics.get("net_sharpe")
        if net_sharpe is not None and net_sharpe < ACTIVATE_MIN_SHARPE:
            return "shadow"
        return "active"
    return "shadow"


def _algorithm_model(name: str):
    if name == "boost":
        return BoostedTrees()
    return LogisticModel(l2=1.0)


def _calibrate(probabilities: list[float], labels: list[int]) -> tuple[list[float], dict[str, Any]]:
    if len(labels) >= ISOTONIC_MIN_SAMPLES:
        points = isotonic_fit(probabilities, labels)
        calibrated = isotonic_apply(points, probabilities)
        return calibrated, {"type": "isotonic", "points": points}
    logits = [logit(value) for value in probabilities]
    a, b = platt_fit(logits, labels)
    calibrated = platt_apply(a, b, logits)
    return calibrated, {"type": "platt", "a": a, "b": b}


def _evaluate(
    algorithm: str,
    dataset: dict[str, Any],
    windows: list[tuple[list[int], list[int]]],
) -> dict[str, Any] | None:
    oos_probability: list[float] = []
    oos_labels: list[int] = []
    oos_returns: list[float] = []
    for train_idx, test_idx in windows:
        model = _algorithm_model(algorithm).fit(
            [dataset["X"][index] for index in train_idx],
            [dataset["y"][index] for index in train_idx],
        )
        oos_probability.extend(model.predict_proba([dataset["X"][index] for index in test_idx]))
        oos_labels.extend(dataset["y"][index] for index in test_idx)
        oos_returns.extend(dataset["returns"][index] for index in test_idx)
    if not oos_probability:
        return None
    calibrated, calibration = _calibrate(oos_probability, oos_labels)
    base_rate = sum(oos_labels) / len(oos_labels)
    metrics: dict[str, Any] = {
        "auc": auc_score(oos_labels, calibrated),
        "brier": brier_score(oos_labels, calibrated),
        "baseline_brier": brier_score(oos_labels, [base_rate] * len(oos_labels)),
        "log_loss": log_loss_score(oos_labels, calibrated),
        "ece": expected_calibration_error(oos_labels, calibrated),
        "base_rate": round(base_rate, 4),
        "n_oos": len(oos_labels),
    }
    metrics.update(economic_metrics(calibrated, oos_returns, horizon_days=dataset.get("horizon", 1)))
    return {
        "algorithm": algorithm,
        "metrics": metrics,
        "calibration": calibration,
        "probabilities": calibrated,
        "labels": oos_labels,
    }


def _eligible(metrics: dict[str, Any]) -> bool:
    """Model kullanilabilir mi: temel Brier'dan iyi ve (varsa) pozitif net Sharpe."""
    brier = metrics.get("brier")
    baseline = metrics.get("baseline_brier")
    if brier is None or baseline is None or brier > baseline:
        return False
    ece = metrics.get("ece")
    if ece is not None and ece > 0.10:
        return False
    sharpe = metrics.get("net_sharpe")
    if sharpe is not None and sharpe <= 0:
        return False
    return True


def _choose(results: dict[str, dict[str, Any]]) -> str:
    """Once saglik kontrolu (Brier<=temel, ECE<=0.10, Sharpe>0); sonra AUC ustunlugu."""
    logreg = results.get("logreg")
    boost = results.get("boost")
    if boost and logreg:
        boost_ok = _eligible(boost["metrics"])
        logreg_ok = _eligible(logreg["metrics"])
        if boost_ok and not logreg_ok:
            return "boost"
        if logreg_ok and not boost_ok:
            return "logreg"
        if logreg_ok and boost_ok:
            boost_auc = boost["metrics"].get("auc") or 0
            logreg_auc = logreg["metrics"].get("auc") or 0
            return "boost" if boost_auc > logreg_auc + 0.005 else "logreg"
    return "boost" if boost else "logreg"


def predict_snapshot(
    snapshot: dict[str, Any],
    params: dict[str, Any],
    extended: dict[int, float] | None = None,
) -> float:
    """Kayitli model parametreleriyle tek anlik goruntu icin olasilik uretir."""
    full_vector = vector_for(snapshot, extended)
    names = params.get("feature_names")
    if names:
        index_map = {name: index for index, name in enumerate(FULL_FEATURE_NAMES)}
        vector = [full_vector[index_map[name]] for name in names if name in index_map]
    else:
        vector = full_vector
    algorithm = params.get("algorithm", "logreg")
    if algorithm == "boost":
        model = BoostedTrees.from_params(params["booster"])
    else:
        model = LogisticModel.from_params(params["logistic"])
    raw = model.predict_proba([vector])[0]
    calibration = params.get("calibration")
    if calibration:
        if calibration.get("type") == "isotonic":
            points = [tuple(point) for point in calibration.get("points") or []]
            if points:
                return isotonic_apply(points, [raw])[0]
        elif calibration.get("type") == "platt":
            return platt_apply(calibration["a"], calibration["b"], [logit(raw)])[0]
    return raw


def _write_predictions(
    db,
    horizon: int,
    model_id: str,
    params: dict[str, Any],
    status: str,
    n_train: int,
    source: str | None = None,
) -> int:
    """Ayni kaynaktaki (live/backfill) kosular icin model tahmini yazar."""
    written = 0
    if source:
        snapshots = db.query(
            "SELECT * FROM feature_snapshots WHERE COALESCE(source, 'live') = ? "
            "ORDER BY created_at DESC LIMIT 2000",
            (source,),
        )
    else:
        snapshots = db.query(
            "SELECT * FROM feature_snapshots ORDER BY created_at DESC LIMIT 2000"
        )
    extended_map = db.extended_features([snapshot["run_id"] for snapshot in snapshots])
    for snapshot in snapshots:
        try:
            probability = predict_snapshot(snapshot, params, extended_map.get(snapshot["run_id"]))
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
    source: str | None = None,
    feature_groups: list[str] | None = None,
) -> dict[str, Any]:
    """Tek ufuk icin model egitir; yetersiz veride egitim yapmaz."""
    rows = db.learning_rows(horizon, coin=coin, source=source)
    extended = db.extended_features([row["run_id"] for row in rows])
    groups = feature_groups or DEFAULT_FEATURE_GROUPS
    dataset = select_features(build_dataset(rows, extended), groups)
    dataset["horizon"] = horizon
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
    algorithms = ["logreg"]
    if n >= BOOST_MIN_SAMPLES:
        algorithms.append("boost")
    results: dict[str, dict[str, Any]] = {}
    for algorithm in algorithms:
        evaluated = _evaluate(algorithm, dataset, windows)
        if evaluated:
            results[algorithm] = evaluated

    if not results:
        return {"status": "no_windows", "horizon_days": horizon, "n": n}

    best = _choose(results)
    chosen = results[best]
    metrics = dict(chosen["metrics"])
    metrics.update(
        {
            "n": n,
            "folds": len(windows),
            "algorithms": list(results),
            "candidates": {
                name: {
                    "auc": item["metrics"].get("auc"),
                    "brier": item["metrics"].get("brier"),
                    "net_sharpe": item["metrics"].get("net_sharpe"),
                }
                for name, item in results.items()
            },
            "feature_count": len(dataset["feature_names"]),
            "feature_groups": groups,
        }
    )
    calibrated_algorithm = chosen["algorithm"]
    calibration = chosen["calibration"]
    bins = probability_bins(chosen["labels"], chosen["probabilities"])

    final_model = _algorithm_model(best).fit(dataset["X"], dataset["y"])
    kind_base = f"{best}_{'iso' if calibration.get('type') == 'isotonic' else 'platt'}"
    kind = f"{kind_base}_bf" if source == "backfill" else kind_base
    model_id = f"{kind}_h{horizon}_{int(time.time())}"
    eligible = _eligible(metrics)
    status = _status_gate(metrics, n, activate_min) if eligible else "rejected"
    if source == "backfill" and status != "rejected":
        status = "shadow"  # tarihsel replay modelleri manuel inceleme ister

    params = {
        "algorithm": best,
        "feature_names": dataset["feature_names"],
        "calibration": calibration,
    }
    if best == "boost":
        params["booster"] = final_model.to_params()
    else:
        params["logistic"] = final_model.to_params()

    notes = (
        f"Purged walk-forward OOS; algoritma={calibrated_algorithm} "
        f"(adaylar: {', '.join(results)}); kalibrasyon={calibration.get('type')}. "
        + ("Egitim: tarihsel replay (backfill)." if source == "backfill" else "Egitim: canli kosular.")
    )
    db.model_save(
        {
            "model_id": model_id,
            "kind": kind,
            "horizon_days": horizon,
            "status": status,
            "trained_at": time.time(),
            "train_rows": n,
            "feature_schema_version": 2,
            "params": json.dumps(params),
            "metrics": json.dumps(metrics),
            "notes": notes,
        }
    )
    if bins:
        db.calibration_bins_save(model_id, horizon, bins)
    written = _write_predictions(db, horizon, model_id, params, status, n, source=source)
    return {
        "status": "trained",
        "model_id": model_id,
        "horizon_days": horizon,
        "n": n,
        "model_status": status,
        "activated": status == "active",
        "source": source or "live",
        "algorithm": best,
        "predictions_written": written,
        "metrics": metrics,
    }


def train_all(
    db,
    *,
    min_samples: int = MIN_SAMPLES,
    source: str | None = None,
    feature_groups: list[str] | None = None,
) -> list[dict[str, Any]]:
    return [
        train_horizon(
            db, horizon, min_samples=min_samples, source=source, feature_groups=feature_groups
        )
        for horizon in (1, 7, 30)
    ]


def latest_model_prediction(db, coin: str, horizon: int = 7) -> dict[str, Any] | None:
    """Aktif/shadow model varsa bu coin icin tahmin uretir."""
    model = db.model_get(horizon)
    snapshot = db.latest_feature_snapshot(coin)
    if not model or not snapshot:
        return None
    try:
        params = json.loads(model.get("params") or "{}")
        extended = db.extended_features([snapshot["run_id"]]).get(snapshot["run_id"])
        probability = predict_snapshot(snapshot, params, extended)
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
