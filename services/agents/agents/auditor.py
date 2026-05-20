"""Agent 2 — The Risk & Compliance Auditor.

Fuses the Forensic Investigator's RAG findings with the raw C++ features
already in CaseState and produces a definitive fraud confidence in [0,1].
Returns a partial dict for LangGraph to merge.
"""

from __future__ import annotations

import math
import re
from typing import Any

from ..state import CaseState


_AUDITOR_TEMPLATE = """You are the **Risk & Compliance Auditor**.

Forensic Investigator notes:
{forensic}

Raw features:
  ofi            = {ofi:.2f}
  realized_vol   = {realized_vol:.5f}
  mid_price      = {mid_price:.2f}
  total_volume   = {total_volume:.0f}
  window_count   = {window_count}
  anomaly_score  = {anomaly_score:.3f}

Top RAG matches:
{match_lines}

Decide a fraud confidence in [0, 1]. Write a short markdown rationale
(<= 6 bullet points) and embed the score in a line of the form
`confidence=<float>` so the orchestrator can read it without re-parsing
your prose. The orchestrator threshold for enforcement is 0.95.
"""


def _format_matches(state: CaseState) -> str:
    if not state.rag_matches:
        return "  (none)"
    return "\n".join(
        f"  - [{m.attack_id}] {m.name}  similarity={m.similarity:.3f}  "
        f"severity={m.severity:.2f}"
        for m in state.rag_matches
    )


_CONF_RE = re.compile(r"confidence\s*=\s*([0-9]*\.?[0-9]+)", re.IGNORECASE)


def _extract_confidence(text: str, fallback: float) -> float:
    """Parse the LLM-emitted `confidence=...` token; clamp to [0, 1]."""
    match = _CONF_RE.search(text or "")
    if not match:
        return fallback
    try:
        score = float(match.group(1))
    except ValueError:
        return fallback
    if math.isnan(score) or math.isinf(score):
        return fallback
    return max(0.0, min(1.0, score))


def _heuristic_confidence(state: CaseState) -> float:
    """Computed when the LLM forgets to embed a `confidence=...` token.

    Blends the classifier's anomaly_score with the strongest RAG match.
    """
    top = max((m.similarity * m.severity for m in state.rag_matches), default=0.0)
    return max(0.0, min(1.0, 0.5 * state.anomaly_score + 0.5 * top))


def risk_auditor(state: CaseState, llm) -> dict[str, Any]:
    prompt = _AUDITOR_TEMPLATE.format(
        forensic=state.forensic_rationale or "(none)",
        ofi=state.features.get("ofi", 0.0),
        realized_vol=state.features.get("realized_vol", 0.0),
        mid_price=state.features.get("mid_price", 0.0),
        total_volume=state.features.get("total_volume", 0.0),
        window_count=int(state.features.get("window_count", 0)),
        anomaly_score=state.anomaly_score,
        match_lines=_format_matches(state),
    )
    response = llm.invoke(prompt)
    content = getattr(response, "content", str(response))
    confidence = _extract_confidence(content, fallback=_heuristic_confidence(state))
    return {
        "confidence": confidence,
        "audit_prompt": prompt,
        "audit_rationale": content,
    }
