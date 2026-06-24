"""Thin PostgreSQL helpers for the classifier service + trainer.

We keep the surface tiny on purpose — only the rows we actually need to
write so the schema in `scripts/sql/init.sql` is the source of truth.

Connection precedence:
  1. DATABASE_URL          (Supabase / any managed Postgres)
  2. PGHOST/PGPORT/...     (libpq env vars; convenient for local dev)
"""

from __future__ import annotations

import os
from typing import Iterable

import psycopg2
from psycopg2.extensions import connection as Connection

from .feature_frame import FeatureFrame


def connect_from_env() -> Connection:
    """Reads DATABASE_URL first, falls back to libpq env vars."""
    if dsn := os.getenv("DATABASE_URL"):
        return psycopg2.connect(dsn, application_name="volatix-classifier")
    return psycopg2.connect(
        host=os.getenv("PGHOST", "localhost"),
        port=int(os.getenv("PGPORT", "5432")),
        user=os.getenv("PGUSER", "postgres"),
        password=os.getenv("PGPASSWORD", ""),
        dbname=os.getenv("PGDATABASE", "postgres"),
        application_name="volatix-classifier",
    )


def insert_feature_log(conn: Connection, frame: FeatureFrame, label: int | None) -> None:
    """Persists one frame for later retraining. `label` is None at write time
    — Airflow joins it with downstream-confirmed labels nightly.
    """
    sql = """
        INSERT INTO feature_log
            (ts_ns, symbol, ofi, realized_vol, mid_price,
             total_volume, window_count, label,
             case_id, wire_ts_ns, compute_ts_ns)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                frame.case_id,
                frame.wire_ts_ns,
                frame.compute_ts_ns,
            ),
        )


def insert_anomaly_score(conn: Connection, frame: FeatureFrame, score: float,
                         model_id: int | None, score_ts_ns: int) -> None:
    sql = """
        INSERT INTO anomaly_score_log
            (ts_ns, symbol, score, model_id,
             case_id, wire_ts_ns, compute_ts_ns, score_ts_ns)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """
    with conn.cursor() as cur:
        cur.execute(
            sql,
            (
                frame.ts_ns,
                frame.symbol,
                score,
                model_id,
                frame.case_id,
                frame.wire_ts_ns,
                frame.compute_ts_ns,
                score_ts_ns,
            ),
        )


def batch_commit(conn: Connection, rows: Iterable[tuple]) -> None:
    """No-op helper kept for the consumer's microbatch path."""
    conn.commit()
