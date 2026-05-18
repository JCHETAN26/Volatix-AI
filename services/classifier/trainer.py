"""Airflow-triggered retraining entrypoint.

Invoked by the KubernetesPodOperator in `airflow/dags/retraining_pipeline.py`.
Reads yesterday's feature_log rows out of PostgreSQL, runs Purged K-Fold
cross-validation, retrains the LightGBM booster, and persists the new
artifact + metrics to the `model_registry` table.
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import os
import sys
from pathlib import Path

import numpy as np

# Allow `python -m classifier.trainer` and `python services/classifier/trainer.py`.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from classifier import db, model as model_module
from classifier.feature_frame import FEATURE_NAMES

log = logging.getLogger("trainer")


def fetch_dataset(conn, day: dt.date) -> tuple[np.ndarray, np.ndarray]:
    """Pulls one day's feature rows + labels from feature_log."""
    sql = """
        SELECT ofi, realized_vol, mid_price, total_volume, window_count, label
        FROM feature_log
        WHERE ts_ns >= EXTRACT(EPOCH FROM %s)::bigint * 1000000000
          AND ts_ns <  EXTRACT(EPOCH FROM %s)::bigint * 1000000000
        ORDER BY ts_ns
    """
    next_day = day + dt.timedelta(days=1)
    with conn.cursor() as cur:
        cur.execute(sql, (day, next_day))
        rows = cur.fetchall()
    if not rows:
        raise SystemExit(f"no feature_log rows for {day}")

    arr = np.asarray(rows, dtype=np.float64)
    X = arr[:, : len(FEATURE_NAMES)]
    y = arr[:, len(FEATURE_NAMES)].astype(np.int8)
    return X, y


def write_registry_row(conn, *, model_path: Path, result: model_module.TrainResult,
                       day: dt.date, model_bytes: bytes) -> int:
    sql = """
        INSERT INTO model_registry
            (created_at, training_day, n_train, n_features,
             cv_auc_mean, cv_auc_std, model_path, model_bytes)
        VALUES (NOW(), %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """
    with conn.cursor() as cur:
        cur.execute(
            sql,
            (
                day,
                result.n_train,
                result.n_features,
                result.cv_auc_mean,
                result.cv_auc_std,
                str(model_path),
                model_bytes,
            ),
        )
        new_id = cur.fetchone()[0]
    conn.commit()
    return new_id


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--day",
        default=os.getenv("TRAIN_DAY"),
        help="UTC date to train on (YYYY-MM-DD). Defaults to yesterday.",
    )
    parser.add_argument(
        "--out",
        default=os.getenv("MODEL_OUT", "/models/latest.txt"),
        help="Filesystem path for the trained booster (default: %(default)s)",
    )
    parser.add_argument("--n-splits", type=int, default=5)
    parser.add_argument("--rounds", type=int, default=500)
    args = parser.parse_args(argv)

    day = dt.date.fromisoformat(args.day) if args.day else (dt.date.today() - dt.timedelta(days=1))
    log.info("training day=%s out=%s", day, args.out)

    conn = db.connect_from_env()
    try:
        X, y = fetch_dataset(conn, day)
        log.info("fetched %d rows; positives=%d", len(X), int(y.sum()))

        result = model_module.train(X, y, n_splits=args.n_splits, num_boost_round=args.rounds)
        log.info(
            "trained: AUC=%.4f±%.4f n_train=%d",
            result.cv_auc_mean,
            result.cv_auc_std,
            result.n_train,
        )

        out_path = Path(args.out)
        model_module.save_booster(result.booster, out_path)
        model_bytes = out_path.read_bytes()
        log.info("wrote model bytes=%d to %s", len(model_bytes), out_path)

        new_id = write_registry_row(
            conn,
            model_path=out_path,
            result=result,
            day=day,
            model_bytes=model_bytes,
        )
        log.info("registered model id=%d", new_id)
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
