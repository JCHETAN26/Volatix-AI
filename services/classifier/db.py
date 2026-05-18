"""Thin PostgreSQL helpers for the classifier service + trainer.

We keep the surface tiny on purpose — only the rows we actually need to
write so the schema in `scripts/sql/init.sql` is the source of truth.
"""

from __future__ import annotations

import os
from typing import Iterable

import psycopg2
from psycopg2.extensions import connection as Connection

from .feature_frame import FeatureFrame


def connect_from_env() -> Connection:
    """Reads standard libpq env vars (PGHOST, PGPORT, PGUSER, PGPASSWORD, PGDATABASE)."""
    return psycopg2.connect(
        host=os.getenv("PGHOST", "chain-db-postgresql.default.svc.cluster.local"),
        port=int(os.getenv("PGPORT", "5432")),
        user=os.getenv("PGUSER", "postgres"),
        password=os.getenv("PGPASSWORD", ""),
        dbname=os.getenv("PGDATABASE", "postgres"),
        application_name="chainguard-classifier",
    )


def insert_feature_log(conn: Connection, frame: FeatureFrame, label: int | None) -> None:
    """Persists one frame for later retraining. `label` is None at write time
    — Airflow joins it with downstream-confirmed labels nightly.
    """
    sql = """
        INSERT INTO feature_log
            (ts_ns, symbol, ofi, realized_vol, mid_price,
             total_volume, window_count, label)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """
    with conn.cursor() as cur:
        cur.execute(
            sql,
            (
                frame.ts_ns,
                frame.symbol,
                frame.ofi,
                frame.realized_vol,
                frame.mid_price,
                frame.total_volume,
                frame.window_count,
                label,
            ),
        )


def insert_anomaly_score(conn: Connection, frame: FeatureFrame, score: float,
                         model_id: int | None) -> None:
    sql = """
        INSERT INTO anomaly_score_log
            (ts_ns, symbol, score, model_id)
        VALUES (%s, %s, %s, %s)
    """
    with conn.cursor() as cur:
        cur.execute(sql, (frame.ts_ns, frame.symbol, score, model_id))


def batch_commit(conn: Connection, rows: Iterable[tuple]) -> None:
    """No-op helper kept for the consumer's microbatch path."""
    conn.commit()
