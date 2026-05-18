"""Round-trip test for the FeatureFrame layout."""

from __future__ import annotations

import struct

import pytest

from classifier.feature_frame import FeatureFrame, FEATURE_NAMES


def test_size_is_64():
    assert FeatureFrame.SIZE == 64


def test_round_trip():
    frame = FeatureFrame(
        version=1,
        window_count=99,
        ts_ns=1_715_923_812_345_000_000,
        symbol="AAPL",
        ofi=12345.5,
        realized_vol=0.0231,
        mid_price=192.34,
        total_volume=8000.0,
    )
    encoded = frame.to_bytes()
    assert len(encoded) == FeatureFrame.SIZE
    decoded = FeatureFrame.from_bytes(encoded)
    assert decoded == frame


def test_symbol_null_padding_stripped():
    # The C++ side null-pads short symbols; we strip those nulls on decode.
    raw = struct.pack(
        "<HHIq8sddddQ",
        1,
        0,
        0,
        0,
        b"MSFT\x00\x00\x00\x00",
        0.0,
        0.0,
        0.0,
        0.0,
        0,
    )
    decoded = FeatureFrame.from_bytes(raw)
    assert decoded.symbol == "MSFT"


def test_feature_vector_order_matches_names():
    frame = FeatureFrame(
        version=1,
        window_count=10,
        ts_ns=0,
        symbol="X",
        ofi=1.0,
        realized_vol=2.0,
        mid_price=3.0,
        total_volume=4.0,
    )
    vec = frame.as_feature_vector()
    assert len(vec) == len(FEATURE_NAMES)
    assert vec == [1.0, 2.0, 3.0, 4.0, 10.0]


def test_rejects_wrong_length():
    with pytest.raises(ValueError):
        FeatureFrame.from_bytes(b"\x00" * 32)
