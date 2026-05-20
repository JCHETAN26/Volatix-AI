"""Round-trip test for the FeatureFrame layout."""

from __future__ import annotations

import struct

import pytest

from classifier.feature_frame import FeatureFrame, FEATURE_NAMES


def test_size_is_80():
    assert FeatureFrame.SIZE == 80


def _sample_frame() -> FeatureFrame:
    return FeatureFrame(
        version=2,
        window_count=99,
        ts_ns=1_715_923_812_345_000_000,
        symbol="AAPL",
        ofi=12345.5,
        realized_vol=0.0231,
        mid_price=192.34,
        total_volume=8000.0,
        case_id=42_000_000_000,
        wire_ts_ns=1_715_923_812_345_000_100,
        compute_ts_ns=1_715_923_812_345_000_500,
    )


def test_round_trip():
    frame = _sample_frame()
    encoded = frame.to_bytes()
    assert len(encoded) == FeatureFrame.SIZE
    decoded = FeatureFrame.from_bytes(encoded)
    assert decoded == frame


def test_symbol_null_padding_stripped():
    # The C++ side null-pads short symbols; we strip those nulls on decode.
    raw = struct.pack(
        "<HHIq8sddddQqq",
        2,
        0,
        0,
        0,
        b"MSFT\x00\x00\x00\x00",
        0.0,
        0.0,
        0.0,
        0.0,
        0,
        0,
        0,
    )
    decoded = FeatureFrame.from_bytes(raw)
    assert decoded.symbol == "MSFT"


def test_feature_vector_order_matches_names():
    frame = _sample_frame()
    vec = frame.as_feature_vector()
    assert len(vec) == len(FEATURE_NAMES)
    assert vec == [
        frame.ofi,
        frame.realized_vol,
        frame.mid_price,
        frame.total_volume,
        float(frame.window_count),
    ]


def test_rejects_wrong_length():
    with pytest.raises(ValueError):
        FeatureFrame.from_bytes(b"\x00" * 64)
    with pytest.raises(ValueError):
        FeatureFrame.from_bytes(b"\x00" * 32)


def test_receipt_timestamps_round_trip():
    """The fields the Microsecond Receipt UI depends on must survive."""
    frame = _sample_frame()
    decoded = FeatureFrame.from_bytes(frame.to_bytes())
    assert decoded.case_id == frame.case_id
    assert decoded.wire_ts_ns == frame.wire_ts_ns
    assert decoded.compute_ts_ns == frame.compute_ts_ns
