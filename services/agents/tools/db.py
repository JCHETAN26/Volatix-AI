"""PostgreSQL writer for the final agent_report row (Phase 4.2).

Connection precedence:
  1. DATABASE_URL          (Supabase / any managed Postgres)
  2. PGHOST/PGPORT/...     (libpq env vars; convenient for local dev)
"""

from __future__ import annotations

import os

import psycopg2
from psycopg2.extensions import connection as Connection
from psycopg2.extras import Json


def connect_from_env() -> Connection:
    if dsn := os.getenv("DATABASE_URL"):
        return psycopg2.connect(dsn, application_name="volatix-agents")
    return psycopg2.connect(
        host=os.getenv("PGHOST", "localhost"),
        port=int(os.getenv("PGPORT", "5432")),
        user=os.getenv("PGUSER", "postgres"),
        password=os.getenv("PGPASSWORD", ""),
        dbname=os.getenv("PGDATABASE", "postgres"),
        application_name="volatix-agents",
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
    pipeline_case_id: int | None = None,
    wire_ts_ns: int | None = None,
    compute_ts_ns: int | None = None,
    score_ts_ns: int | None = None,
    verdict_ts_ns: int | None = None,
    enforced_ts_ns: int | None = None,
) -> int:
    sql = """
        INSERT INTO agent_report
            (case_id, symbol, ts_ns, anomaly_score, confidence, enforced,
             rationale_md, evidence,
             pipeline_case_id, wire_ts_ns, compute_ts_ns, score_ts_ns,
             verdict_ts_ns, enforced_ts_ns)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s)
        ON CONFLICT (case_id) DO UPDATE SET
            confidence       = EXCLUDED.confidence,
            enforced         = EXCLUDED.enforced,
            rationale_md     = EXCLUDED.rationale_md,
            evidence         = EXCLUDED.evidence,
            pipeline_case_id = COALESCE(EXCLUDED.pipeline_case_id, agent_report.pipeline_case_id),
            wire_ts_ns       = COALESCE(EXCLUDED.wire_ts_ns,       agent_report.wire_ts_ns),
            compute_ts_ns    = COALESCE(EXCLUDED.compute_ts_ns,    agent_report.compute_ts_ns),
            score_ts_ns      = COALESCE(EXCLUDED.score_ts_ns,      agent_report.score_ts_ns),
            verdict_ts_ns    = COALESCE(EXCLUDED.verdict_ts_ns,    agent_report.verdict_ts_ns),
            enforced_ts_ns   = COALESCE(EXCLUDED.enforced_ts_ns,   agent_report.enforced_ts_ns)
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
                pipeline_case_id,
                wire_ts_ns,
                compute_ts_ns,
                score_ts_ns,
                verdict_ts_ns,
                enforced_ts_ns,
            ),
        )
        new_id = cur.fetchone()[0]
    conn.commit()
    return new_id
