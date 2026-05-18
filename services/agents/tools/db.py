"""PostgreSQL writer for the final agent_report row (Phase 4.2)."""

from __future__ import annotations

import json
import os

import psycopg2
from psycopg2.extensions import connection as Connection
from psycopg2.extras import Json


def connect_from_env() -> Connection:
    return psycopg2.connect(
        host=os.getenv("PGHOST", "chain-db-postgresql.default.svc.cluster.local"),
        port=int(os.getenv("PGPORT", "5432")),
        user=os.getenv("PGUSER", "postgres"),
        password=os.getenv("PGPASSWORD", ""),
        dbname=os.getenv("PGDATABASE", "postgres"),
        application_name="chainguard-agents",
    )


def insert_agent_report(
    conn: Connection,
    *,
    case_id,
    symbol: str,
    ts_ns: int,
    anomaly_score: float,
    confidence: float,
    enforced: bool,
    rationale_md: str,
    evidence: dict,
) -> int:
    sql = """
        INSERT INTO agent_report
            (case_id, symbol, ts_ns, anomaly_score, confidence, enforced,
             rationale_md, evidence)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (case_id) DO UPDATE SET
            confidence    = EXCLUDED.confidence,
            enforced      = EXCLUDED.enforced,
            rationale_md  = EXCLUDED.rationale_md,
            evidence      = EXCLUDED.evidence
        RETURNING id
    """
    with conn.cursor() as cur:
        cur.execute(
            sql,
            (
                str(case_id),
                symbol,
                ts_ns,
                anomaly_score,
                confidence,
                enforced,
                rationale_md,
                Json(evidence),
            ),
        )
        new_id = cur.fetchone()[0]
    conn.commit()
    return new_id
