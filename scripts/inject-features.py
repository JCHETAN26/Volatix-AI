#!/usr/bin/env python3
"""ChainGuard-Core — direct Kafka feature injector (Phase 5.2 timing test).

Bypasses the WebSocket + C++ engine path and publishes a small burst of
hand-crafted `FeatureFrame` records directly to the `financial-features`
topic. Used by `scripts/end-to-end.sh` to measure the classifier → agents
→ Postgres latency without needing a host-side C++ runtime.

The 64-byte binary layout is locked against `src/feature_frame.hpp` (and
the classifier's `services/classifier/feature_frame.py`). Anomaly-flavored
defaults: very large OFI, elevated realized vol, lopsided volume.

Usage:
    pip install kafka-python
    python3 scripts/inject-features.py                  # 5 frames default
    python3 scripts/inject-features.py --count 50 --symbol AAPL
    python3 scripts/inject-features.py --brokers chain-kafka:9092 --topic financial-features
"""

from __future__ import annotations

import argparse
import struct
import sys
import time

try:
    from kafka import KafkaProducer
except ImportError as exc:  # pragma: no cover
    raise SystemExit("missing dependency: pip install kafka-python") from exc


# Must stay in sync with src/feature_frame.hpp (#pragma pack(1), 64 bytes).
_STRUCT = struct.Struct("<HHIq8sddddQ")
assert _STRUCT.size == 64, f"layout drift: {_STRUCT.size} != 64"

FRAME_VERSION = 1
TOPIC = "financial-features"
DEFAULT_BROKERS = "localhost:9092"
SYMBOL_MAX = 8


def _encode(symbol: str, ts_ns: int, *, ofi: float, rv: float,
            mid: float, total_volume: float, window_count: int) -> bytes:
    sym = symbol.encode("ascii")[:SYMBOL_MAX].ljust(SYMBOL_MAX, b"\x00")
    return _STRUCT.pack(
        FRAME_VERSION,    # version
        0,                # _pad0
        window_count,     # window_count
        ts_ns,            # ts_ns
        sym,              # symbol
        ofi,              # ofi
        rv,               # realized_vol
        mid,              # mid_price
        total_volume,     # total_volume
        0,                # _pad1
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--brokers", default=DEFAULT_BROKERS)
    parser.add_argument("--topic", default=TOPIC)
    parser.add_argument("--symbol", default="AAPL")
    parser.add_argument("--count", type=int, default=5,
                        help="frames to emit (default: 5)")
    parser.add_argument("--ofi", type=float, default=12_500.0,
                        help="OFI per frame; >8000 will score high-risk in baseline (default: 12500)")
    parser.add_argument("--realized-vol", type=float, default=0.07)
    parser.add_argument("--mid-price", type=float, default=192.0)
    parser.add_argument("--total-volume", type=float, default=65_000.0)
    parser.add_argument("--window-count", type=int, default=120)
    args = parser.parse_args(argv)

    if args.count <= 0:
        parser.error("--count must be > 0")

    producer = KafkaProducer(
        bootstrap_servers=args.brokers,
        client_id="chainguard-inject-features",
        linger_ms=0,        # ship immediately for the timing test
        acks="all",
    )

    t0 = time.monotonic()
    for i in range(args.count):
        ts_ns = time.time_ns()
        payload = _encode(
            args.symbol,
            ts_ns,
            ofi=args.ofi,
            rv=args.realized_vol,
            mid=args.mid_price + i * 0.05,   # tiny ramp so RV stays positive downstream
            total_volume=args.total_volume,
            window_count=args.window_count,
        )
        producer.send(args.topic, key=args.symbol.encode("ascii"), value=payload)
    producer.flush(timeout=5.0)
    dt = time.monotonic() - t0

    print(f"injected {args.count} frame(s) into {args.brokers}/{args.topic} in {dt*1000:.1f}ms")
    print(f"  symbol={args.symbol} ofi={args.ofi} rv={args.realized_vol} "
          f"mid={args.mid_price} vol={args.total_volume}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
