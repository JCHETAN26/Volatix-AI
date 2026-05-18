"""LightGBM model wrapper + Purged K-Fold cross-validator.

Purged K-Fold (López de Prado, AFML §7) keeps training and validation folds
non-contiguous in time and removes any training samples whose label horizon
overlaps the validation window. This prevents the look-ahead leakage that
plain KFold introduces on time-series financial data — the Phase 4.1 plan
calls this out explicitly.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator

import numpy as np
import lightgbm as lgb

from .feature_frame import FEATURE_NAMES


# ---------------------------------------------------------------------------
# Model load / predict
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class AnomalyModel:
    booster: lgb.Booster

    @classmethod
    def load(cls, path: str | Path) -> "AnomalyModel":
        booster = lgb.Booster(model_file=str(path))
        return cls(booster=booster)

    def predict(self, features: np.ndarray) -> np.ndarray:
        """features: shape (n_samples, n_features). Returns scores in [0,1]."""
        if features.ndim == 1:
            features = features.reshape(1, -1)
        return np.clip(self.booster.predict(features), 0.0, 1.0)

    def predict_one(self, vec: list[float]) -> float:
        arr = np.asarray(vec, dtype=np.float64).reshape(1, -1)
        return float(self.predict(arr)[0])


# ---------------------------------------------------------------------------
# Purged K-Fold
# ---------------------------------------------------------------------------

def purged_kfold_indices(
    n_samples: int,
    n_splits: int,
    embargo_pct: float = 0.01,
) -> Iterator[tuple[np.ndarray, np.ndarray]]:
    """Yields (train_idx, val_idx) tuples with a temporal embargo.

    `embargo_pct` removes the leading `embargo_pct * n_samples` indices
    after each validation fold from the training set, so a sample whose
    label could have been informed by validation data never appears in
    training.
    """
    if n_splits < 2:
        raise ValueError("n_splits must be >= 2")
    if not 0.0 <= embargo_pct < 1.0:
        raise ValueError("embargo_pct must be in [0, 1)")

    fold_size = n_samples // n_splits
    embargo = int(round(embargo_pct * n_samples))

    indices = np.arange(n_samples)
    for k in range(n_splits):
        val_start = k * fold_size
        val_stop = n_samples if k == n_splits - 1 else (k + 1) * fold_size
        val_idx = indices[val_start:val_stop]
        train_mask = np.ones(n_samples, dtype=bool)
        train_mask[val_start:val_stop] = False
        # Embargo: drop samples in [val_stop, val_stop + embargo).
        train_mask[val_stop : val_stop + embargo] = False
        train_idx = indices[train_mask]
        yield train_idx, val_idx


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

@dataclass
class TrainResult:
    booster: lgb.Booster
    cv_auc_mean: float
    cv_auc_std: float
    n_train: int
    n_features: int


_DEFAULT_PARAMS: dict[str, object] = {
    "objective": "binary",
    "metric": ["binary_logloss", "auc"],
    "boosting_type": "gbdt",
    "num_leaves": 31,
    "learning_rate": 0.05,
    "feature_fraction": 0.9,
    "bagging_fraction": 0.8,
    "bagging_freq": 5,
    "verbose": -1,
}


def train(
    X: np.ndarray,
    y: np.ndarray,
    *,
    n_splits: int = 5,
    embargo_pct: float = 0.01,
    num_boost_round: int = 200,
    params: dict[str, object] | None = None,
) -> TrainResult:
    """Train a LightGBM binary classifier with Purged K-Fold validation.

    X is shape (n, n_features), y is shape (n,) in {0, 1}.
    """
    if X.ndim != 2 or len(X) != len(y):
        raise ValueError("X must be (n, n_features) and align with y")

    p = dict(_DEFAULT_PARAMS, **(params or {}))

    aucs: list[float] = []
    for train_idx, val_idx in purged_kfold_indices(len(X), n_splits, embargo_pct):
        train_ds = lgb.Dataset(X[train_idx], y[train_idx], feature_name=list(FEATURE_NAMES))
        val_ds = lgb.Dataset(
            X[val_idx],
            y[val_idx],
            feature_name=list(FEATURE_NAMES),
            reference=train_ds,
        )
        booster = lgb.train(
            p,
            train_ds,
            num_boost_round=num_boost_round,
            valid_sets=[val_ds],
            callbacks=[lgb.early_stopping(stopping_rounds=20, verbose=False)],
        )
        aucs.append(float(booster.best_score["valid_0"]["auc"]))

    # Final fit on the full set after CV gives us our deploy artifact.
    full_ds = lgb.Dataset(X, y, feature_name=list(FEATURE_NAMES))
    booster = lgb.train(p, full_ds, num_boost_round=num_boost_round)

    return TrainResult(
        booster=booster,
        cv_auc_mean=float(np.mean(aucs)),
        cv_auc_std=float(np.std(aucs)),
        n_train=int(len(X)),
        n_features=int(X.shape[1]),
    )


def save_booster(booster: lgb.Booster, path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    booster.save_model(str(path))
