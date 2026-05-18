"""LangGraph wiring for the 3-tier agent cluster (Phase 4.2).

    [forensic] → [auditor] ─ confidence ≥ 0.95 ─→ [enforcer] → END
                       │
                       └── confidence  < 0.95 ──→ [no_enforce_finalize] → END
"""

from __future__ import annotations

from typing import Any, Callable

from langgraph.graph import END, StateGraph

from .agents.auditor import risk_auditor
from .agents.enforcer import compose_final_report, settlement_enforcer
from .agents.forensic import forensic_investigator
from .state import CaseState
from .tools.rag import QdrantRag


ENFORCEMENT_GATE = 0.95


def build_graph(llm, rag: QdrantRag) -> Callable[[CaseState], dict[str, Any]]:
    """Returns a compiled LangGraph runnable; pass it a CaseState dict."""
    graph: StateGraph = StateGraph(CaseState)

    graph.add_node("forensic", lambda s: forensic_investigator(s, llm, rag))
    graph.add_node("auditor", lambda s: risk_auditor(s, llm))
    graph.add_node("enforcer", lambda s: settlement_enforcer(s, llm))
    graph.add_node("no_enforce_finalize", lambda s: compose_final_report(s, enforced=False))

    graph.set_entry_point("forensic")
    graph.add_edge("forensic", "auditor")

    def route_after_audit(state: CaseState) -> str:
        return "enforcer" if state.confidence >= ENFORCEMENT_GATE else "no_enforce_finalize"

    graph.add_conditional_edges(
        "auditor",
        route_after_audit,
        {
            "enforcer": "enforcer",
            "no_enforce_finalize": "no_enforce_finalize",
        },
    )
    graph.add_edge("enforcer", END)
    graph.add_edge("no_enforce_finalize", END)

    return graph.compile()
