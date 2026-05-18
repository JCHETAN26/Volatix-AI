#!/usr/bin/env python3
"""Generate the baseline LightGBM anomaly model.

The streaming consumer needs *some* model on disk before any real feature
data exists. This script builds one from `synthetic.make_dataset` so the
service can boot cold; the Airflow DAG (Phase 4.1 / Task 4.1) replaces it
nightly with one trained on real PostgreSQL feature logs.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow `python scripts/train_baseline.py` from the service root.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from classifier import model as model_module
from classifier import synthetic


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        default="services/classifier/models/baseline.txt",
        help="Output path for the LightGBM booster (default: %(default)s)",
    )
    parser.add_argument("--n", type=int, default=20_000, help="Synthetic sample count")
    parser.add_argument("--anomaly-rate", type=float, default=0.05)
    parser.add_argument("--n-splits", type=int, default=5)
    parser.add_argument("--rounds", type=int, default=200)
    args = parser.parse_args(argv)

    X, y = synthetic.make_dataset(n=args.n, anomaly_rate=args.anomaly_rate)
    print(f"synthesized {len(X)} samples ({y.sum()} anomalies)")

    result = model_module.train(
        X,
        y,
        n_splits=args.n_splits,
        num_boost_round=args.rounds,
    )
    print(
        f"purged k-fold AUC: mean={result.cv_auc_mean:.4f} "
        f"std={result.cv_auc_std:.4f}  n_train={result.n_train}"
    )

    out = Path(args.out)
    model_module.save_booster(result.booster, out)
    print(f"wrote {out} ({out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
