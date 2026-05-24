"""Postgres writes for the eval runner.

Mirrors ``agents.tools.db``'s connection pattern (``DATABASE_URL`` env)
but writes to the Phase 6 tables: ``eval_run`` + ``eval_case_result``.

Single transaction per run — either the whole batch lands or none of it,
so the dashboard never reads a partial result set.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Optional

import psycopg2
import psycopg2.extras

log = logging.getLogger(__name__)


def connect_from_env():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL not set; cannot write eval results")
    return psycopg2.connect(url)


def write_run(
    conn,
    *,
    prompt_version: str,
    fixture_revision: str,
    llm_provider: str,
    llm_model: str,
    n_cases: int,
    freeze_correctness: Optional[float],
    faithfulness: Optional[float],
    answer_relevancy: Optional[float],
    p50_latency_ms: Optional[float],
    p95_latency_ms: Optional[float],
    notes: str,
    case_rows: list[dict[str, Any]],
) -> int:
    """Insert eval_run + N eval_case_result rows in one transaction."""
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO eval_run (
                    prompt_version, fixture_revision, llm_provider, llm_model,
                    n_cases, freeze_correctness, faithfulness, answer_relevancy,
                    p50_latency_ms, p95_latency_ms, notes
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    prompt_version, fixture_revision, llm_provider, llm_model,
                    n_cases, freeze_correctness, faithfulness, answer_relevancy,
                    p50_latency_ms, p95_latency_ms, notes,
                ),
            )
            run_id = cur.fetchone()[0]
            psycopg2.extras.execute_values(
                cur,
                """
                INSERT INTO eval_case_result (
                    eval_run_id, case_id, expected_action, actual_action,
                    correct, faithfulness, answer_relevancy, latency_ms,
                    agent_output
                )
                VALUES %s
                """,
                [
                    (
                        run_id,
                        r["case_id"],
                        r["expected_action"],
                        r.get("actual_action"),
                        bool(r["correct"]),
                        r.get("faithfulness"),
                        r.get("answer_relevancy"),
                        r.get("latency_ms"),
                        json.dumps(r.get("agent_output", {})),
                    )
                    for r in case_rows
                ],
            )
    return run_id
