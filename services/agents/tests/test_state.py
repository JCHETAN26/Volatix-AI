"""CaseState schema + feature-vector ordering."""

from __future__ import annotations

import uuid

from agents.state import FEATURE_NAMES, CaseState


def _make_case(**overrides) -> CaseState:
    defaults = dict(
        case_id=uuid.UUID(int=1),
        symbol="AAPL",
        ts_ns=1_715_923_812_345_000_000,
        anomaly_score=0.91,
        features={
            "ofi": 1234.5,
            "realized_vol": 0.0231,
            "mid_price": 192.34,
            "total_volume": 80000.0,
            "window_count": 100,
        },
    )
    defaults.update(overrides)
    return CaseState(**defaults)


def test_feature_vector_order_matches_feature_names():
    state = _make_case()
    vec = state.feature_vector()
    assert len(vec) == len(FEATURE_NAMES)
    assert vec == [
        state.features["ofi"],
        state.features["realized_vol"],
        state.features["mid_price"],
        state.features["total_volume"],
        state.features["window_count"],
    ]


def test_missing_features_default_to_zero():
    state = _make_case(features={"ofi": 100.0})
    vec = state.feature_vector()
    assert vec[0] == 100.0
    assert vec[1:] == [0.0, 0.0, 0.0, 0.0]


def test_enforcement_field_starts_unset():
    state = _make_case()
    assert state.enforcement_action is None
    assert state.confidence == 0.0
    assert state.rationale_md == ""
