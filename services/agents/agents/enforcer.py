"""Agent 3 — The Settlement & Enforcer.

Reached only when the Risk & Compliance Auditor's confidence ≥ 0.95.
Compiles a structured freeze instruction (account or symbol halt),
composes the final markdown audit report, and persists it to PostgreSQL
`agent_report`.

This node also runs in the "no enforcement" terminal path: when the
auditor's confidence is below the gate, `compose_final_report` is called
directly from graph.py so we still write a row marking the case as
reviewed-but-not-enforced.
"""

from __future__ import annotations

import time
from typing import Any

from ..state import CaseState, EnforcementAction


_ENFORCER_TEMPLATE = """You are the **Settlement & Enforcer**.

The Risk & Compliance Auditor scored this case at confidence={confidence:.3f},
which clears the 0.95 enforcement gate. Compile:

1. A structured freeze instruction (action, target, reason_code, notes).
2. A final markdown audit report that combines the Forensic Investigator's
   findings, the Auditor's rationale, and your enforcement decision.

Case context:
  symbol         = {symbol}
  ts_ns          = {ts_ns}
  anomaly_score  = {anomaly_score:.3f}

Forensic notes:
{forensic}

Auditor notes:
{auditor}

Return the markdown report; the orchestrator will attach the structured
action separately.
"""


def _default_action(state: CaseState) -> EnforcementAction:
    """Conservative default action used when the LLM doesn't propose one."""
    reason = "HIGH_CONFIDENCE_ANOMALY"
    if state.rag_matches:
        top = max(state.rag_matches, key=lambda m: m.similarity * m.severity)
        reason = f"MATCH_{top.attack_id.upper()}"
    return EnforcementAction(
        action="HALT_SYMBOL",
        target=state.symbol,
        reason_code=reason,
        notes=(
            f"Triggered at confidence={state.confidence:.3f} "
            f"(anomaly_score={state.anomaly_score:.3f})."
        ),
    )


def _compose_final_md(state: CaseState, enforced: bool) -> str:
    lines: list[str] = [
        f"# ChainGuard Audit Report — case {state.case_id}",
        "",
        f"- **symbol**: `{state.symbol}`",
        f"- **ts_ns**: {state.ts_ns}",
        f"- **anomaly_score**: {state.anomaly_score:.3f}",
        f"- **confidence**: {state.confidence:.3f}",
        f"- **enforced**: {enforced}",
        "",
        "## Forensic Investigator",
        state.forensic_rationale.strip() or "_(none)_",
        "",
        "## Risk & Compliance Auditor",
        state.audit_rationale.strip() or "_(none)_",
    ]
    if enforced:
        lines += [
            "",
            "## Settlement & Enforcer",
            state.enforcement_rationale.strip() or "_(none)_",
        ]
        if state.enforcement_action is not None:
            a = state.enforcement_action
            lines += [
                "",
                "### Action",
                f"- action: `{a.action}`",
                f"- target: `{a.target}`",
                f"- reason_code: `{a.reason_code}`",
                f"- notes: {a.notes}",
            ]
    return "\n".join(lines)


def compose_final_report(state: CaseState, enforced: bool) -> dict[str, Any]:
    """Used by the graph for the unenforced terminal path."""
    return {"rationale_md": _compose_final_md(state, enforced)}


def settlement_enforcer(state: CaseState, llm) -> dict[str, Any]:
    prompt = _ENFORCER_TEMPLATE.format(
        confidence=state.confidence,
        symbol=state.symbol,
        ts_ns=state.ts_ns,
        anomaly_score=state.anomaly_score,
        forensic=state.forensic_rationale or "(none)",
        auditor=state.audit_rationale or "(none)",
    )
    response = llm.invoke(prompt)
    enforcement_md = getattr(response, "content", str(response))
    action = _default_action(state)
    enforced_ts_ns = time.time_ns()  # T+4 for the Receipt UI

    # Build the final markdown using a *patched* CaseState so the helper
    # sees the freshly produced enforcement fields.
    patched = state.model_copy(
        update={
            "enforcement_action": action,
            "enforcement_rationale": enforcement_md,
            "enforced_ts_ns": enforced_ts_ns,
        }
    )
    return {
        "enforcement_action": action,
        "enforcement_rationale": enforcement_md,
        "enforced_ts_ns": enforced_ts_ns,
        "rationale_md": _compose_final_md(patched, enforced=True),
    }
