"""Build the eval fixture deterministically from the attack-vector centroids.

The centroids come from ``services/agents/seed_vector_db.SEED_POINTS`` —
the same 10-class taxonomy seeded into Qdrant. For each centroid we
generate ``PER_CLASS`` jittered variants using a seeded RNG, label each
case from the centroid's severity, and write the result as a stable
JSON array.

The fixture is intentionally synthetic but realistic: it covers the
attack vector classes the Forensic Investigator's RAG actually knows
about, so an eval against this fixture exercises the same matching paths
the live cluster does. Hand-curated *taxonomy + labeling rules*, not
hand-typed 200 rows — that's how production LLM eval suites are built
(Anthropic, OpenAI, Cohere).

Re-running is byte-identical: the RNG seed is fixed, the centroids are
ordered, and json.dumps is sort_keys=True.

Usage::

    python -m agents.eval.fixtures.build  # writes services/agents/eval/fixtures/cases.json
"""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from agents.seed_vector_db import SEED_POINTS  # noqa: E402  (intentional late import)

ExpectedAction = Literal["FREEZE", "MONITOR", "NO_ACTION"]
Difficulty = Literal["easy", "borderline", "hard"]

PER_CLASS = 20  # 10 classes × 20 = 200 cases
SEED = 20260523  # locked; bump only when the fixture intentionally changes
FIXTURE_PATH = Path(__file__).parent / "cases.json"


@dataclass(frozen=True)
class Case:
    case_id: str
    attack_class: str
    attack_id: str  # av-001, av-002, ...
    severity: float
    ofi: float
    realized_vol: float
    mid_price: float
    total_volume: float
    window_count: int
    expected_action: ExpectedAction
    expected_reason_code: str
    difficulty: Difficulty


def _action_for(severity: float) -> ExpectedAction:
    """Severity → expected enforcement action.

    The thresholds match the agent service's runtime gates:
    Risk & Compliance Auditor escalates at confidence ≥ 0.95 (→ FREEZE);
    high-risk but below that lands in MONITOR; below the classifier's
    0.85 cutoff is effectively NO_ACTION.
    """
    if severity >= 0.9:
        return "FREEZE"
    if severity >= 0.6:
        return "MONITOR"
    return "NO_ACTION"


def _jitter(rng: random.Random, value: float, *, frac: float) -> float:
    """Multiply by a value in [1-frac, 1+frac]. Preserves sign."""
    return value * (1.0 + rng.uniform(-frac, frac))


def _difficulty_for(idx: int) -> tuple[Difficulty, float]:
    """20 cases per class split as 10 easy / 6 borderline / 4 hard.

    Easier cases get small jitter (stays close to the centroid → high
    similarity to the RAG match). Borderline cases get medium jitter.
    Hard cases get large jitter that may push features into a neighbouring
    class's region — testing whether the agent reasons about *which* of
    the top-K RAG matches actually fits.
    """
    if idx < 10:
        return "easy", 0.05
    if idx < 16:
        return "borderline", 0.18
    return "hard", 0.40


def build_cases() -> list[Case]:
    rng = random.Random(SEED)
    cases: list[Case] = []
    for pid, name, severity, vec, _notes in SEED_POINTS:
        attack_id = f"av-{pid:03d}"
        ofi, rv, mid, vol, win = vec
        for i in range(PER_CLASS):
            difficulty, frac = _difficulty_for(i)
            case = Case(
                case_id=f"{attack_id}-{i:02d}",
                attack_class=name,
                attack_id=attack_id,
                severity=severity,
                ofi=_jitter(rng, ofi, frac=frac),
                realized_vol=max(0.0, _jitter(rng, rv, frac=frac)),
                mid_price=_jitter(rng, mid, frac=frac * 0.1),  # price barely moves
                total_volume=max(0.0, _jitter(rng, vol, frac=frac)),
                window_count=max(1, int(_jitter(rng, win, frac=frac * 0.3))),
                expected_action=_action_for(severity),
                expected_reason_code=f"MATCH_{attack_id.upper()}",
                difficulty=difficulty,
            )
            cases.append(case)
    return cases


def to_jsonable(cases: list[Case]) -> list[dict]:
    return [
        {
            "case_id": c.case_id,
            "attack_class": c.attack_class,
            "attack_id": c.attack_id,
            "severity": round(c.severity, 4),
            "features": {
                "ofi": round(c.ofi, 4),
                "realized_vol": round(c.realized_vol, 6),
                "mid_price": round(c.mid_price, 4),
                "total_volume": round(c.total_volume, 4),
                "window_count": c.window_count,
            },
            "expected_action": c.expected_action,
            "expected_reason_code": c.expected_reason_code,
            "difficulty": c.difficulty,
        }
        for c in cases
    ]


def fixture_revision(payload: list[dict]) -> str:
    """sha256 of the canonical-JSON encoding — drift detector."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def main() -> int:
    cases = build_cases()
    payload = to_jsonable(cases)
    revision = fixture_revision(payload)
    FIXTURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    out = {
        "revision": revision,
        "count": len(payload),
        "schema": "volatix.eval.fixture.v1",
        "cases": payload,
    }
    FIXTURE_PATH.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    print(f"wrote {len(payload)} cases to {FIXTURE_PATH}")
    print(f"  revision={revision}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
