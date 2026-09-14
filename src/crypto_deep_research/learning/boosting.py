"""Kompakt gradyan artirma (karar agaclari) - saf NumPy, dis bagimlilik yok.

Logloss gradyani ile derinlik 1-2 agaclar egitir; bolunme aramasi vektorize
edilmistir (her ozellik icin siralama + kumulatif toplam).
"""

from __future__ import annotations

from typing import Any

import numpy as np


def _sigmoid(values: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(values, -30.0, 30.0)))


def _best_split(
    X: np.ndarray, gradient: np.ndarray, hessian: np.ndarray, min_leaf: int, l2: float
) -> tuple[int, float, np.ndarray] | None:
    n = len(gradient)
    parent = (float(gradient.sum()) ** 2) / (float(hessian.sum()) + l2)
    best: tuple[float, int, float, np.ndarray] | None = None
    for feature in range(X.shape[1]):
        column = X[:, feature]
        order = np.argsort(column, kind="mergesort")
        xs = column[order]
        gs = gradient[order]
        hs = hessian[order]
        cum_g = np.cumsum(gs)
        cum_h = np.cumsum(hs)
        counts = np.arange(1, n)
        right_counts = n - counts
        left_gain = (cum_g[:-1] ** 2) / (cum_h[:-1] + l2)
        right_gain = ((cum_g[-1] - cum_g[:-1]) ** 2) / ((cum_h[-1] - cum_h[:-1]) + l2)
        gains = left_gain + right_gain - parent
        valid = (xs[:-1] < xs[1:]) & (counts >= min_leaf) & (right_counts >= min_leaf)
        if not np.any(valid):
            continue
        masked = np.where(valid, gains, -np.inf)
        index = int(np.argmax(masked))
        if best is None or masked[index] > best[0]:
            threshold = float((xs[index] + xs[index + 1]) / 2)
            mask = column <= threshold
            best = (float(masked[index]), feature, threshold, mask)
    if best is None:
        return None
    return best[1], best[2], best[3]


class BoostedTrees:
    """Ikili siniflandirma icin gradyan artirma (logloss, Newton yaprak degeri)."""

    def __init__(
        self,
        rounds: int = 150,
        learning_rate: float = 0.1,
        max_depth: int = 2,
        min_leaf: int = 25,
        l2: float = 1.0,
    ) -> None:
        self.rounds = rounds
        self.learning_rate = learning_rate
        self.max_depth = max_depth
        self.min_leaf = min_leaf
        self.l2 = l2

    def fit(self, X: Any, y: Any) -> BoostedTrees:
        features = np.asarray(X, dtype=float)
        labels = np.asarray(y, dtype=float)
        prior = float(np.clip(labels.mean(), 1e-6, 1 - 1e-6))
        self.base = float(np.log(prior / (1 - prior)))
        prediction = np.full(len(labels), self.base)
        self.trees: list[dict[str, Any]] = []
        for _ in range(self.rounds):
            probabilities = _sigmoid(prediction)
            gradient = labels - probabilities
            hessian = np.maximum(probabilities * (1 - probabilities), 1e-6)
            tree = self._build(features, gradient, hessian, self.max_depth)
            prediction += self.learning_rate * self._apply(tree, features)
            self.trees.append(tree)
        return self

    def _leaf(self, gradient: np.ndarray, hessian: np.ndarray) -> dict[str, float]:
        return {"leaf": float(gradient.sum() / (hessian.sum() + self.l2))}

    def _build(
        self, X: np.ndarray, gradient: np.ndarray, hessian: np.ndarray, depth: int
    ) -> dict[str, Any]:
        if depth <= 0 or len(gradient) < 2 * self.min_leaf:
            return self._leaf(gradient, hessian)
        split = _best_split(X, gradient, hessian, self.min_leaf, self.l2)
        if split is None:
            return self._leaf(gradient, hessian)
        feature, threshold, mask = split
        return {
            "feature": feature,
            "threshold": threshold,
            "left": self._build(X[mask], gradient[mask], hessian[mask], depth - 1),
            "right": self._build(X[~mask], gradient[~mask], hessian[~mask], depth - 1),
        }

    def _apply(self, tree: dict[str, Any], X: np.ndarray) -> np.ndarray:
        if "leaf" in tree:
            return np.full(X.shape[0], tree["leaf"])
        mask = X[:, tree["feature"]] <= tree["threshold"]
        output = np.empty(X.shape[0])
        if np.any(mask):
            output[mask] = self._apply(tree["left"], X[mask])
        if np.any(~mask):
            output[~mask] = self._apply(tree["right"], X[~mask])
        return output

    def predict_proba(self, X: Any) -> list[float]:
        features = np.asarray(X, dtype=float)
        prediction = np.full(features.shape[0], self.base)
        for tree in self.trees:
            prediction += self.learning_rate * self._apply(tree, features)
        return _sigmoid(prediction).tolist()

    def to_params(self) -> dict[str, Any]:
        return {
            "rounds": self.rounds,
            "learning_rate": self.learning_rate,
            "max_depth": self.max_depth,
            "min_leaf": self.min_leaf,
            "l2": self.l2,
            "base": self.base,
            "trees": self.trees,
        }

    @classmethod
    def from_params(cls, params: dict[str, Any]) -> BoostedTrees:
        model = cls(
            rounds=params.get("rounds", 150),
            learning_rate=params.get("learning_rate", 0.1),
            max_depth=params.get("max_depth", 2),
            min_leaf=params.get("min_leaf", 25),
            l2=params.get("l2", 1.0),
        )
        model.base = float(params.get("base", 0.0))
        model.trees = list(params.get("trees", []))
        return model
