"""LangGraph state carried through the 3-tier agent cluster (Phase 4.2).

Field ownership (kept here so the agent nodes can stay short):

  Phase 0 — input               case_id, symbol, ts_ns, anomaly_score, features
  Phase 1 — forensic            rag_matches, forensic_rationale
  Phase 2 — auditor             confidence, audit_rationale
  Phase 3 — enforcer (gated)    enforcement_action, enforcement_rationale
  Final                         rationale_md (composed by the enforcer or, when
                                gated off, the auditor)
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

FEATURE_NAMES: tuple[str, ...] = (
    "ofi",
    "realized_vol",
    "mid_price",
    "total_volume",
    "window_count",
)


class AttackMatch(BaseModel):
    """A single Qdrant search result describing a known exploit pattern."""

    attack_id: str
    name: str
    severity: float  # 0..1, payload-defined
    similarity: float  # 0..1, from Qdrant's cosine score


class EnforcementAction(BaseModel):
    """Structured freeze instruction emitted by the Settlement & Enforcer."""

    action: str  # e.g. "FREEZE_ACCOUNT", "HALT_SYMBOL"
    target: str  # symbol / account id
    reason_code: str
    notes: str = ""


class CaseState(BaseModel):
    # --- Input populated by the consumer ---------------------------------
    case_id: UUID
    symbol: str
    ts_ns: int
    anomaly_score: float
    features: dict[str, float] = Field(default_factory=dict)

    # --- Forensic Investigator ------------------------------------------
    rag_matches: list[AttackMatch] = Field(default_factory=list)
    forensic_rationale: str = ""

    # --- Risk & Compliance Auditor --------------------------------------
    confidence: float = 0.0
    audit_rationale: str = ""

    # --- Settlement & Enforcer (conditional) -----------------------------
    enforcement_action: Optional[EnforcementAction] = None
    enforcement_rationale: str = ""

    # --- Final composed report ------------------------------------------
    rationale_md: str = ""

    def feature_vector(self) -> list[float]:
        """Order-locked vector for Qdrant search; must match seed_vector_db.py."""
        return [float(self.features.get(name, 0.0)) for name in FEATURE_NAMES]
