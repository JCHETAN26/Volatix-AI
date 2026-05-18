"""Deterministic synthetic data for baseline training + tests.

The real training corpus comes from PostgreSQL `feature_log` populated by the
streaming consumer. This module is only used:
  - by `scripts/train_baseline.py` to seed a starter model so the service
    can boot before any real data exists;
  - by tests to keep them reproducible.
"""

from __future__ import annotations

import numpy as np

from .feature_frame import FEATURE_NAMES


def make_dataset(n: int = 20_000, anomaly_rate: float = 0.05, seed: int = 42):
    """Returns (X, y) where y=1 represents a market-shock anomaly.

    Normal regime: small OFI, moderate volatility, balanced volume.
    Shock regime : large absolute OFI, elevated volatility, lopsided volume.
    """
    rng = np.random.default_rng(seed)
    n_anom = int(round(n * anomaly_rate))
    n_norm = n - n_anom

    # Normal samples.
    ofi_n = rng.normal(0.0, 500.0, n_norm)
    rv_n = rng.lognormal(mean=-5.0, sigma=0.4, size=n_norm)
    mid_n = rng.normal(190.0, 1.5, n_norm)
    vol_n = rng.lognormal(mean=8.0, sigma=0.3, size=n_norm)
    cnt_n = rng.integers(30, 120, n_norm).astype(np.float64)

    # Anomaly samples — shifted distributions across all features.
    sign = rng.choice([-1.0, 1.0], n_anom)
    ofi_a = sign * rng.normal(8000.0, 1500.0, n_anom)
    rv_a = rng.lognormal(mean=-3.0, sigma=0.5, size=n_anom)
    mid_a = rng.normal(190.0, 4.0, n_anom)
    vol_a = rng.lognormal(mean=10.0, sigma=0.4, size=n_anom)
    cnt_a = rng.integers(60, 128, n_anom).astype(np.float64)

    X = np.empty((n, len(FEATURE_NAMES)), dtype=np.float64)
    y = np.zeros(n, dtype=np.int8)

    X[:n_norm, 0] = ofi_n
    X[:n_norm, 1] = rv_n
    X[:n_norm, 2] = mid_n
    X[:n_norm, 3] = vol_n
    X[:n_norm, 4] = cnt_n

    X[n_norm:, 0] = ofi_a
    X[n_norm:, 1] = rv_a
    X[n_norm:, 2] = mid_a
    X[n_norm:, 3] = vol_a
    X[n_norm:, 4] = cnt_a
    y[n_norm:] = 1

    # Shuffle but keep order deterministic.
    perm = rng.permutation(n)
    return X[perm], y[perm]
