"""Agent 1 — The Forensic Investigator.

Triggered for every CaseState that reaches the graph (the consumer already
gates on classifier `high_risk=true`). Pulls the top-K most similar attack
vectors out of Qdrant and asks the LLM for a short markdown rationale.

The node returns a *partial dict* — LangGraph merges it into the running
CaseState — rather than mutating, to keep the graph pure-functional.
"""

from __future__ import annotations

from typing import Any

from ..state import AttackMatch, CaseState
from ..tools.rag import QdrantRag


_FORENSIC_TEMPLATE = """You are the **Forensic Investigator** in a financial
threat triage pipeline.

Case under review:
  symbol         = {symbol}
  ts_ns          = {ts_ns}
  anomaly_score  = {anomaly_score:.3f}
  features       = ofi={ofi:.2f}, realized_vol={realized_vol:.4f}, \
mid_price={mid_price:.2f}, total_volume={total_volume:.0f}, \
window_count={window_count}

Top RAG matches against the historic exploit corpus:
{match_lines}

Write a tight markdown rationale (<= 6 bullet points) describing:
- whether any match looks plausible given the live features;
- what additional evidence the next agent should weigh;
- any caveats.

Do NOT assign a confidence score yourself — that is the Risk & Compliance
Auditor's job.
"""


def _format_matches(matches: list[AttackMatch]) -> str:
    if not matches:
        return "  (no matches above similarity floor)"
    lines = []
    for m in matches:
        lines.append(
            f"  - [{m.attack_id}] {m.name}  similarity={m.similarity:.3f}  "
            f"severity={m.severity:.2f}"
        )
    return "\n".join(lines)


def _parse_search_result(raw: list[dict[str, Any]]) -> list[AttackMatch]:
    matches: list[AttackMatch] = []
    for item in raw:
        payload = item.get("payload") or {}
        matches.append(
            AttackMatch(
                attack_id=str(payload.get("attack_id", item.get("id", "?"))),
                name=str(payload.get("name", "unknown")),
                severity=float(payload.get("severity", 0.5)),
                similarity=float(item.get("score", 0.0)),
            )
        )
    return matches


def forensic_investigator(state: CaseState, llm, rag: QdrantRag) -> dict[str, Any]:
    raw = rag.search(state.feature_vector(), limit=3)
    matches = _parse_search_result(raw)

    prompt = _FORENSIC_TEMPLATE.format(
        symbol=state.symbol,
        ts_ns=state.ts_ns,
        anomaly_score=state.anomaly_score,
        ofi=state.features.get("ofi", 0.0),
        realized_vol=state.features.get("realized_vol", 0.0),
        mid_price=state.features.get("mid_price", 0.0),
        total_volume=state.features.get("total_volume", 0.0),
        window_count=int(state.features.get("window_count", 0)),
        match_lines=_format_matches(matches),
    )
    response = llm.invoke(prompt)
    return {
        "rag_matches": matches,
        "forensic_rationale": getattr(response, "content", str(response)),
    }
