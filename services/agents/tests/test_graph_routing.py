"""End-to-end graph routing with the MockChatLLM + a stub Qdrant.

This is the closest thing we have to a unit test for the 3-tier wiring
without spinning up an LLM or a Qdrant pod. It exercises:

  - the forensic node calling the (mocked) Qdrant
  - the conditional edge after the auditor (enforce vs. finalize)
  - the enforcer composing a markdown report and a structured action
"""

from __future__ import annotations

import uuid

from agents.graph import build_graph
from agents.llm import MockChatLLM
from agents.state import CaseState


class StubRag:
    """Mimics QdrantRag.search() with hand-rolled matches per query."""

    def __init__(self, response):
        self._response = response

    def search(self, vector, limit: int = 3):
        return self._response

    def close(self):
        pass


def _features(ofi: float, realized_vol: float = 0.05) -> dict[str, float]:
    return {
        "ofi": ofi,
        "realized_vol": realized_vol,
        "mid_price": 192.0,
        "total_volume": 60000.0,
        "window_count": 110,
    }


def _initial_state(ofi: float, realized_vol: float = 0.05) -> CaseState:
    return CaseState(
        case_id=uuid.uuid4(),
        symbol="AAPL",
        ts_ns=1_715_923_812_345_000_000,
        anomaly_score=0.92,
        features=_features(ofi, realized_vol),
    )


def _qdrant_response(score: float = 0.97):
    return [
        {
            "id": 1,
            "score": score,
            "payload": {
                "attack_id": "av-001",
                "name": "Flash-Loan Imbalance",
                "severity": 0.95,
            },
        }
    ]


def test_high_confidence_path_enforces():
    """Big OFI in the prompt → mock auditor pushes confidence over 0.95."""
    llm = MockChatLLM()
    rag = StubRag(_qdrant_response(score=0.99))
    graph = build_graph(llm, rag)

    state = _initial_state(ofi=18_500.0, realized_vol=0.08)
    final = CaseState.model_validate(graph.invoke(state))

    assert final.confidence >= 0.95
    assert final.enforcement_action is not None
    assert final.enforcement_action.target == "AAPL"
    assert "# ChainGuard Audit Report" in final.rationale_md
    assert "enforced: True" in final.rationale_md


def test_low_confidence_path_skips_enforcer():
    """Tiny OFI → confidence stays below 0.95 → no enforcement action."""
    llm = MockChatLLM()
    rag = StubRag(_qdrant_response(score=0.10))
    graph = build_graph(llm, rag)

    state = _initial_state(ofi=10.0, realized_vol=0.001)
    final = CaseState.model_validate(graph.invoke(state))

    assert final.confidence < 0.95
    assert final.enforcement_action is None
    assert "# ChainGuard Audit Report" in final.rationale_md
    assert "enforced: False" in final.rationale_md
