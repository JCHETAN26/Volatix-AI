#!/usr/bin/env python3
"""Volatix-AI — mock WebSocket ticker (Phase 2.2 dev fixture).

Emits Polygon-flavored JSON tick records on every connected client at a
configurable rate. Used to exercise the C++ --ingest path locally without
needing a live Polygon.io subscription.

Wire schema (one JSON document per WebSocket text frame):
  {"sym":"AAPL","t":1715923812345000000,"p":192.34,"s":100,"side":"B"}

Usage:
  pip install websockets
  python3 scripts/mock-ticker.py                  # 25k tps on ws://0.0.0.0:8765/
  python3 scripts/mock-ticker.py --rate 50000     # crank it up
  python3 scripts/mock-ticker.py --port 9001 --rate 1000 --inject-malformed 5
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import signal
import time
from typing import Iterable

try:
    import websockets
except ImportError as exc:  # pragma: no cover - install hint
    raise SystemExit("missing dependency: pip install websockets") from exc


SYMBOLS = ("AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "GOOG", "META", "AMD")


def _next_payload(seq: int) -> str:
    sym = SYMBOLS[seq % len(SYMBOLS)]
    price = round(100.0 + (seq % 5000) * 0.01, 2)
    size_shares = 100 + (seq % 500)
    ts_ns = time.time_ns()
    side = "B" if seq & 1 else "S"
    return json.dumps({"sym": sym, "t": ts_ns, "p": price, "s": size_shares, "side": side})


def _malformed_payload() -> str:
    # Three flavors of brokenness so the parser's "degrade gracefully"
    # acceptance line gets meaningfully exercised.
    choice = random.choice(("truncated", "wrong-type", "missing-field"))
    if choice == "truncated":
        return '{"sym":"AAPL","t":1715923812345000000,"p":192.3'
    if choice == "wrong-type":
        return '{"sym":"AAPL","t":"not-a-number","p":192.34,"s":100}'
    return '{"sym":"AAPL","p":192.34,"s":100}'  # missing t


async def _stream(ws, rate: int, malformed_per_thousand: int) -> None:
    seq = 0
    # Burst in fixed-size batches to amortize asyncio yield cost. At
    # rate=25_000 with batch=500, that's 50 awaits/sec — comfortable.
    batch = max(1, min(500, rate))
    period = batch / float(rate)
    while True:
        for _ in range(batch):
            if malformed_per_thousand > 0 and (seq % 1000) < malformed_per_thousand:
                payload = _malformed_payload()
            else:
                payload = _next_payload(seq)
            seq += 1
            try:
                await ws.send(payload)
            except websockets.ConnectionClosed:
                return
        await asyncio.sleep(period)


def _build_handler(rate: int, malformed_per_thousand: int):
    async def handler(ws):
        peer = ws.remote_address
        print(f"  + client connected from {peer}")
        try:
            await _stream(ws, rate, malformed_per_thousand)
        finally:
            print(f"  - client {peer} disconnected")
    return handler


async def _serve(host: str, port: int, rate: int, malformed_per_thousand: int) -> None:
    handler = _build_handler(rate, malformed_per_thousand)
    async with websockets.serve(handler, host, port, max_size=2 ** 20):
        print(f"mock-ticker listening on ws://{host}:{port}/")
        print(f"  rate              = {rate} ticks/sec")
        print(f"  malformed/1000    = {malformed_per_thousand}")
        print("Press Ctrl-C to stop.")
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop.set)
        await stop.wait()


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--rate", type=int, default=25_000,
                        help="ticks/sec (default: 25000)")
    parser.add_argument("--inject-malformed", type=int, default=0,
                        dest="malformed_per_thousand", metavar="N",
                        help="emit N malformed payloads per 1000 (default: 0)")
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.rate <= 0:
        parser.error("--rate must be > 0")
    if not 0 <= args.malformed_per_thousand <= 1000:
        parser.error("--inject-malformed must be between 0 and 1000")

    try:
        asyncio.run(_serve(args.host, args.port, args.rate, args.malformed_per_thousand))
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
