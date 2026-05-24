"""Per-case scoring: binary correctness + Ragas LLM-as-judge metrics.

``score_case`` returns a dict with the three headline metrics:

  * ``freeze_correctness`` — boolean: did the Enforcer's action match
    the fixture's ``expected_action``? Always computed.
  * ``faithfulness`` — float in [0, 1]: does the auditor's rationale
    cite the Qdrant RAG-retrieved attack vectors, or hallucinate?
    Requires Ragas + a judge LLM. ``None`` if Ragas isn't available.
  * ``answer_relevancy`` — float in [0, 1]: does the rationale address
    the actual feature vector, or wander? Same Ragas dependency.

Ragas is a heavy import (LangChain + datasets + a judge LLM). Lazy-
loaded so the rest of the runner can still produce binary metrics if
Ragas fails to install or initialize.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from agents.state import CaseState

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Action mapping — fixture labels vs. live Enforcer outputs.
# ---------------------------------------------------------------------------
# Fixture labels are the three high-level decisions:
#   FREEZE / MONITOR / NO_ACTION
# The Enforcer's EnforcementAction.action is the specific verb the agent
# emitted (HALT_SYMBOL, FREEZE_ACCOUNT, …). We collapse both sides to
# the fixture's vocabulary for the binary correctness check.
_FREEZE_TOKENS = {"FREEZE", "FREEZE_ACCOUNT", "HALT_SYMBOL", "HALT"}


def normalize_action(state: CaseState) -> str:
    """Collapse the agent's terminal state to FREEZE / MONITOR / NO_ACTION.

    Rules (in order):
      * enforcer ran and emitted an action          → FREEZE
      * auditor confidence ≥ 0.85 but enforcer skipped → MONITOR
      * else                                        → NO_ACTION
    """
    if state.enforcement_action is not None:
        verb = state.enforcement_action.action.upper()
        if verb in _FREEZE_TOKENS or "FREEZE" in verb or "HALT" in verb:
            return "FREEZE"
    if state.confidence >= 0.85:
        return "MONITOR"
    return "NO_ACTION"


# ---------------------------------------------------------------------------
# Ragas wrapper. Lazy import; everything still works without it.
# ---------------------------------------------------------------------------

_ragas_singleton: Optional[dict[str, Any]] = None


def _get_ragas() -> Optional[dict[str, Any]]:
    """Build a single (faithfulness, answer_relevancy, judge_llm, embedder) bundle.

    Ragas defaults to OpenAI for both the judge LLM AND for the embedding
    model that powers ``answer_relevancy``. We don't ship an OpenAI key,
    so both have to be explicitly swapped to whatever provider made the
    judge LLM — usually Gemini in this project.
    """
    global _ragas_singleton
    if _ragas_singleton is not None:
        return _ragas_singleton if _ragas_singleton.get("ok") else None
    try:
        import os

        from ragas import evaluate  # type: ignore
        from ragas.embeddings import LangchainEmbeddingsWrapper  # type: ignore
        from ragas.llms import LangchainLLMWrapper  # type: ignore
        from ragas.metrics import answer_relevancy, faithfulness  # type: ignore
        from datasets import Dataset  # type: ignore

        from agents.llm import make_chat_llm

        judge_llm = LangchainLLMWrapper(make_chat_llm())

        # Embedder: prefer Gemini if GOOGLE_API_KEY is set; fall back to a
        # local sentence-transformers model so the eval doesn't silently
        # NaN when there's no embedding API available. Without one of
        # these, answer_relevancy returns NaN.
        embedder = None
        if os.getenv("GOOGLE_API_KEY"):
            try:
                from langchain_google_genai import (  # type: ignore
                    GoogleGenerativeAIEmbeddings,
                )

                # `gemini-embedding-001` is the current production embedder
                # on the v1beta API (as of mid-2026). Previous models
                # `text-embedding-004` and `embedding-001` are both 404 now.
                # Overridable via $EVAL_EMBED_MODEL for forward-compat.
                embed_model = os.getenv(
                    "EVAL_EMBED_MODEL", "models/gemini-embedding-001"
                )
                embedder = LangchainEmbeddingsWrapper(
                    GoogleGenerativeAIEmbeddings(
                        model=embed_model,
                        google_api_key=os.environ["GOOGLE_API_KEY"],
                    )
                )
            except Exception as exc:  # pragma: no cover - missing optional dep
                log.warning("Gemini embedder unavailable: %s", exc)

        _ragas_singleton = {
            "ok": True,
            "evaluate": evaluate,
            "Dataset": Dataset,
            "faithfulness": faithfulness,
            "answer_relevancy": answer_relevancy,
            "judge": judge_llm,
            "embedder": embedder,
        }
    except Exception as exc:  # pragma: no cover - missing optional dep
        log.warning("Ragas unavailable, qualitative metrics will be null: %s", exc)
        _ragas_singleton = {"ok": False}
        return None
    return _ragas_singleton


def _features_as_question(state: CaseState) -> str:
    """Render the feature vector as a natural-language question for Ragas."""
    f = state.features
    return (
        f"A trading frame on symbol {state.symbol} produced these features: "
        f"order_flow_imbalance={f.get('ofi', 0):.2f}, "
        f"realized_volatility={f.get('realized_vol', 0):.4f}, "
        f"mid_price={f.get('mid_price', 0):.2f}, "
        f"total_volume={f.get('total_volume', 0):.2f}, "
        f"window_count={int(f.get('window_count', 0))}. "
        "Is this indicative of market manipulation, and if so which class?"
    )


def _rag_matches_as_contexts(state: CaseState) -> list[str]:
    return [
        f"[{m.attack_id}] {m.name} — similarity {m.similarity:.3f}, "
        f"severity {m.severity:.2f}"
        for m in state.rag_matches
    ]


def ragas_metrics(state: CaseState) -> dict[str, Optional[float]]:
    """Compute faithfulness + answer_relevancy for one case via Ragas.

    Returns ``{"faithfulness": None, "answer_relevancy": None}`` if Ragas
    isn't installed or the auditor produced no rationale.
    """
    null = {"faithfulness": None, "answer_relevancy": None}
    if not state.audit_rationale:
        return null
    bundle = _get_ragas()
    if bundle is None:
        return null
    try:
        ds = bundle["Dataset"].from_list(
            [
                {
                    "user_input": _features_as_question(state),
                    "response": state.audit_rationale,
                    "retrieved_contexts": _rag_matches_as_contexts(state) or ["(no rag matches)"],
                }
            ]
        )
        # answer_relevancy needs an embedder; if none configured, drop it
        # rather than NaN-out the metric.
        metrics = [bundle["faithfulness"]]
        if bundle.get("embedder") is not None:
            metrics.append(bundle["answer_relevancy"])
        kwargs: dict[str, Any] = {
            "dataset": ds,
            "metrics": metrics,
            "llm": bundle["judge"],
            "show_progress": False,
        }
        if bundle.get("embedder") is not None:
            kwargs["embeddings"] = bundle["embedder"]
        result = bundle["evaluate"](**kwargs)
        scores = result.scores[0] if hasattr(result, "scores") else result[0]
        return {
            "faithfulness": float(scores.get("faithfulness", 0.0)) if scores.get("faithfulness") is not None else None,
            "answer_relevancy": float(scores.get("answer_relevancy", 0.0)) if scores.get("answer_relevancy") is not None else None,
        }
    except Exception as exc:
        log.warning("ragas scoring failed for case: %s", exc)
        return null


def score_case(state: CaseState, expected_action: str) -> dict[str, Any]:
    """Roll up everything we want stored per case."""
    actual = normalize_action(state)
    correct = actual == expected_action
    ragas = ragas_metrics(state)
    return {
        "actual_action": actual,
        "correct": correct,
        "faithfulness": ragas["faithfulness"],
        "answer_relevancy": ragas["answer_relevancy"],
    }
