"""Wire-compatible decoder for the C++ FeatureFrame.

Layout v2 (must match src/feature_frame.hpp byte-for-byte):

    offset  field           type    bytes
    0       version         u16     2
    2       _pad0           u16     2
    4       window_count    u32     4
    8       ts_ns           i64     8
    16      symbol          char[8] 8
    24      ofi             f64     8
    32      realized_vol    f64     8
    40      mid_price       f64     8
    48      total_volume    f64     8
    56      case_id         u64     8
    64      wire_ts_ns      i64     8
    72      compute_ts_ns   i64     8
    --------------------------------- 80

Little-endian, packed. The C++ side serializes with `#pragma pack(push, 1)`
and a static_assert(sizeof == 80), so any drift will fail at compile time
on that side; this struct format is the matching contract.

`case_id`, `wire_ts_ns`, and `compute_ts_ns` are populated by the engine
post-1.0 — older frames (v1) would have None there if we still saw any
in the wild, but the consumer fails fast on any size mismatch.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import ClassVar


_STRUCT = struct.Struct("<HHIq8sddddQqq")
assert _STRUCT.size == 80, f"FeatureFrame layout drifted: {_STRUCT.size} != 80"


@dataclass(frozen=True, slots=True)
class FeatureFrame:
    version: int
    window_count: int
    ts_ns: int
    symbol: str
    ofi: float
    realized_vol: float
    mid_price: float
    total_volume: float
    case_id: int
    wire_ts_ns: int
    compute_ts_ns: int

    SIZE: ClassVar[int] = 80

    @classmethod
    def from_bytes(cls, payload: bytes) -> "FeatureFrame":
        if len(payload) != cls.SIZE:
            raise ValueError(f"expected {cls.SIZE} bytes, got {len(payload)}")
        (
            version,
            _pad0,
            window_count,
            ts_ns,
            symbol_raw,
            ofi,
            realized_vol,
            mid_price,
            total_volume,
            case_id,
            wire_ts_ns,
            compute_ts_ns,
        ) = _STRUCT.unpack(payload)
        symbol = symbol_raw.rstrip(b"\x00").decode("ascii", errors="replace")
        return cls(
            version=version,
            window_count=window_count,
            ts_ns=ts_ns,
            symbol=symbol,
            ofi=ofi,
            realized_vol=realized_vol,
            mid_price=mid_price,
            total_volume=total_volume,
            case_id=case_id,
            wire_ts_ns=wire_ts_ns,
            compute_ts_ns=compute_ts_ns,
        )

    def to_bytes(self) -> bytes:
        # Mainly used for testing — production messages come from the C++
        # engine.
        sym = self.symbol.encode("ascii")[:8].ljust(8, b"\x00")
        return _STRUCT.pack(
            self.version,
            0,  # _pad0
            self.window_count,
            self.ts_ns,
            sym,
            self.ofi,
            self.realized_vol,
            self.mid_price,
            self.total_volume,
            self.case_id,
            self.wire_ts_ns,
            self.compute_ts_ns,
        )

    def as_feature_vector(self) -> list[float]:
        """Order is locked — train_baseline + classifier must agree."""
        return [
            self.ofi,
            self.realized_vol,
            self.mid_price,
            self.total_volume,
            float(self.window_count),
        ]


FEATURE_NAMES: tuple[str, ...] = (
    "ofi",
    "realized_vol",
    "mid_price",
    "total_volume",
    "window_count",
)
