"""Replay the eval fixture through the LangGraph cluster + score it.

This bypasses Kafka entirely: each fixture case is materialized into a
``CaseState`` and fed straight into the compiled graph. The graph still
calls real Qdrant (the Forensic Investigator's RAG search) and the real
LLM provider, so the run measures the same code path the live system
takes — minus the streaming layer.

Outputs:
  * one ``eval_run`` row with rolled-up metrics
  * N ``eval_case_result`` rows with per-case scoring + full agent
    output JSONB for the dashboard drilldown

Run locally (against a port-forwarded cluster)::

    DATABASE_URL=... \\
    GOOGLE_API_KEY=... \\
    QDRANT_URL=http://localhost:6333 \\
    python -m agents.eval.runner --limit 20

Run inside the cluster (Airflow KubernetesPodOperator)::

    python -m agents.eval.runner    # picks up QDRANT_URL + DATABASE_URL
                                    # from the agents-config ConfigMap
"""

from __future__ import annotations

import argparse
import logging
import os
import statistics
import sys
import time
import uuid
from typing import Any

from agents.eval.fixtures import load_cases
from agents.eval.scoring import score_case
from agents.eval.storage import connect_from_env, write_run
from agents.graph import build_graph
from agents.llm import make_chat_llm
from agents.state import CaseState
from agents.tools.rag import QdrantRag

log = logging.getLogger("eval.runner")

PROMPT_VERSION_ENV = "PROMPT_VERSION"
DEFAULT_PROMPT_VERSION = "v0"


def _case_to_state(case: dict[str, Any]) -> CaseState:
    """Build a CaseState the graph can consume from one fixture case.

    The fixture doesn't include an anomaly_score — it represents *what
    would have arrived at the agents if the classifier had let it through* —
    so we synthesize one from the centroid severity. The live pipeline
    only invokes agents for high_risk frames, so >=0.85 is the realistic
    floor.
    """
    return CaseState(
        case_id=uuid.uuid4(),
        symbol=case["case_id"].upper(),
        ts_ns=time.time_ns(),
        anomaly_score=max(0.85, float(case["severity"])),
        features=dict(case["features"]),
    )


def _summarize(case_results: list[dict[str, Any]]) -> dict[str, Any]:
    """Roll up the per-case scores into the eval_run columns."""
    n = len(case_results)
    if n == 0:
        return {
            "freeze_correctness": None,
            "faithfulness": None,
            "answer_relevancy": None,
            "p50_latency_ms": None,
            "p95_latency_ms": None,
        }
    correct = [1.0 if r["correct"] else 0.0 for r in case_results]
    faiths = [r["faithfulness"] for r in case_results if r.get("faithfulness") is not None]
    rels = [r["answer_relevancy"] for r in case_results if r.get("answer_relevancy") is not None]
    lats = sorted([r["latency_ms"] for r in case_results if r.get("latency_ms") is not None])

    def pct(arr: list[float], p: float) -> float | None:
        if not arr:
            return None
        k = max(0, min(len(arr) - 1, int(round((p / 100.0) * (len(arr) - 1)))))
        return arr[k]

    return {
        "freeze_correctness": sum(correct) / n,
        "faithfulness": (sum(faiths) / len(faiths)) if faiths else None,
        "answer_relevancy": (sum(rels) / len(rels)) if rels else None,
        "p50_latency_ms": pct(lats, 50),
        "p95_latency_ms": pct(lats, 95),
    }


def run_eval(*, limit: int | None, dry_run: bool, notes: str) -> int:
    """Return the eval_run row id, or 0 on dry-run."""
    fixture = load_cases()
    cases = fixture["cases"]
    if limit is not None:
        cases = cases[:limit]
    revision = fixture["revision"]
    prompt_version = os.environ.get(PROMPT_VERSION_ENV, DEFAULT_PROMPT_VERSION)
    llm_provider = os.environ.get("LLM_PROVIDER") or (
        "gemini" if os.environ.get("GOOGLE_API_KEY")
        else "openai" if os.environ.get("OPENAI_API_KEY")
        else "mock"
    )
    llm_model = os.environ.get("LLM_MODEL", "gemini-2.5-flash")

    log.info(
        "eval starting: cases=%d prompt_version=%s provider=%s model=%s revision=%s",
        len(cases), prompt_version, llm_provider, llm_model, revision[:12],
    )

    llm = make_chat_llm()
    rag = QdrantRag()
    graph = build_graph(llm, rag)

    case_results: list[dict[str, Any]] = []
    t_start = time.monotonic()
    for i, case in enumerate(cases):
        state = _case_to_state(case)
        t0 = time.monotonic()
        try:
            final = graph.invoke(state)
            final_state = CaseState.model_validate(final)
        except Exception as exc:
            log.warning("graph invocation failed for case %s: %s", case["case_id"], exc)
            case_results.append({
                "case_id": case["case_id"],
                "expected_action": case["expected_action"],
                "actual_action": None,
                "correct": False,
                "faithfulness": None,
                "answer_relevancy": None,
                "latency_ms": (time.monotonic() - t0) * 1000.0,
                "agent_output": {"error": str(exc)},
            })
            continue
        latency_ms = (time.monotonic() - t0) * 1000.0
        scores = score_case(final_state, case["expected_action"])
        case_results.append({
            "case_id": case["case_id"],
            "expected_action": case["expected_action"],
            "actual_action": scores["actual_action"],
            "correct": scores["correct"],
            "faithfulness": scores["faithfulness"],
            "answer_relevancy": scores["answer_relevancy"],
            "latency_ms": latency_ms,
            "agent_output": {
                "rationale_md": final_state.rationale_md,
                "confidence": final_state.confidence,
                "enforcement_action": (
                    final_state.enforcement_action.model_dump()
                    if final_state.enforcement_action is not None
                    else None
                ),
                "rag_matches": [m.model_dump() for m in final_state.rag_matches],
            },
        })
        if (i + 1) % 10 == 0:
            log.info("progress: %d/%d", i + 1, len(cases))

    summary = _summarize(case_results)
    elapsed = time.monotonic() - t_start
    log.info(
        "eval done in %.1fs: freeze_correctness=%s faithfulness=%s answer_relevancy=%s",
        elapsed,
        f"{summary['freeze_correctness']:.3f}" if summary["freeze_correctness"] is not None else "—",
        f"{summary['faithfulness']:.3f}" if summary["faithfulness"] is not None else "—",
        f"{summary['answer_relevancy']:.3f}" if summary["answer_relevancy"] is not None else "—",
    )

    if dry_run:
        log.info("dry-run: skipping DB write")
        rag.close()
        return 0

    conn = connect_from_env()
    try:
        run_id = write_run(
            conn,
            prompt_version=prompt_version,
            fixture_revision=revision,
            llm_provider=llm_provider,
            llm_model=llm_model,
            n_cases=len(case_results),
            notes=notes,
            case_rows=case_results,
            **summary,
        )
        log.info("wrote eval_run id=%d (+ %d eval_case_result rows)",
                 run_id, len(case_results))
        return run_id
    finally:
        conn.close()
        rag.close()


def main() -> int:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None,
                        help="Only run the first N cases (smoke testing).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Skip the DB write; just print summary.")
    parser.add_argument("--notes", default="",
                        help="Free-text note stored on the eval_run row.")
    args = parser.parse_args()
    run_eval(limit=args.limit, dry_run=args.dry_run, notes=args.notes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
