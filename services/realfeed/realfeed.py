#!/usr/bin/env python3
"""ChainGuard-Core — Coinbase Exchange WS → ChainGuard schema adapter.

Connects to wss://ws-feed.exchange.coinbase.com (public, no API key
required), subscribes to the `matches` channel for one or more product
IDs (e.g. BTC-USD), and re-emits each filled trade onto a local
WebSocket server on port 8765 — the same interface the engine's
WsClient already speaks via mock-ticker.py.

Translation:
    Coinbase match    → ChainGuard tick
    ──────────────────────────────────────────────────────────────
    product_id "BTC-USD"  → sym "BTC"   (8-char field, truncated)
    price (string)        → p (float)
    size (string)         → s (uint32)  scaled ×100 so a 0.05 BTC
                                        trade reads as 5 "share-eq"
    side  "buy" / "sell"  → "B" / "S"
    received-at           → t (ns since epoch)

The wire schema downstream is unchanged — the C++ simdjson parser
sees the exact same JSON shape as it does with mock-ticker.

Env knobs:
    COINBASE_URL     default wss://ws-feed.exchange.coinbase.com
    PRODUCTS         comma-separated list, default "BTC-USD"
    PORT             local WS port to expose, default 8765
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import time
from typing import Iterable

try:
    import websockets
    from websockets.exceptions import ConnectionClosed
except ImportError as exc:  # pragma: no cover
    raise SystemExit("missing dependency: pip install websockets") from exc


log = logging.getLogger("realfeed")

COINBASE_URL = os.getenv("COINBASE_URL", "wss://ws-feed.exchange.coinbase.com")
PRODUCTS: tuple[str, ...] = tuple(
    p.strip() for p in os.getenv("PRODUCTS", "BTC-USD").split(",") if p.strip()
)
PORT = int(os.getenv("PORT", "8765"))


# Local subscribers we re-emit to. Set-based so we can drop dead sockets.
_clients: set[websockets.WebSocketServerProtocol] = set()


def _adapt(match: dict) -> str | None:
    """Coinbase match → ChainGuard tick JSON. Returns None on malformed input."""
    try:
        product = str(match["product_id"])
        sym = product.split("-", 1)[0][:8]  # "BTC-USD" → "BTC"; fits the 8-byte symbol field
        price = float(match["price"])
        size = float(match["size"])
        size_shares = max(1, int(size * 100))  # 0.05 BTC → 5 share-equivalents
        side = "B" if match.get("side") == "buy" else "S"
        return json.dumps({
            "sym": sym,
            "t": time.time_ns(),
            "p": price,
            "s": size_shares,
            "side": side,
        })
    except (KeyError, ValueError, TypeError) as exc:
        log.debug("dropping malformed match: %s", exc)
        return None


async def _broadcast(payload: str) -> None:
    if not _clients:
        return
    dead: list[websockets.WebSocketServerProtocol] = []
    for client in _clients:
        try:
            await client.send(payload)
        except ConnectionClosed:
            dead.append(client)
    for client in dead:
        _clients.discard(client)


async def _upstream_loop(products: Iterable[str]) -> None:
    """Maintains a persistent Coinbase subscription with reconnect."""
    subscribe_msg = json.dumps({
        "type": "subscribe",
        "product_ids": list(products),
        "channels": ["matches"],
    })
    backoff_s = 1.0
    while True:
        try:
            async with websockets.connect(COINBASE_URL, ping_interval=30) as ws:
                await ws.send(subscribe_msg)
                log.info("subscribed to Coinbase matches for %s", list(products))
                backoff_s = 1.0  # reset on a successful connect
                async for raw in ws:
                    try:
                        msg = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    if msg.get("type") != "match":
                        continue
                    payload = _adapt(msg)
                    if payload is not None:
                        await _broadcast(payload)
        except (ConnectionClosed, OSError) as exc:
            log.warning("upstream dropped (%s); reconnecting in %.1fs", exc, backoff_s)
            await asyncio.sleep(backoff_s)
            backoff_s = min(backoff_s * 2, 30.0)


async def _handler(ws: websockets.WebSocketServerProtocol) -> None:
    peer = ws.remote_address
    log.info("client connected from %s", peer)
    _clients.add(ws)
    try:
        await ws.wait_closed()
    finally:
        _clients.discard(ws)
        log.info("client %s disconnected", peer)


async def _serve() -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    server = await websockets.serve(_handler, "0.0.0.0", PORT, max_size=2 ** 20)
    log.info("realfeed listening on ws://0.0.0.0:%d/  products=%s", PORT, list(PRODUCTS))

    upstream = asyncio.create_task(_upstream_loop(PRODUCTS))
    stopped = asyncio.create_task(stop.wait())

    done, pending = await asyncio.wait(
        {upstream, stopped}, return_when=asyncio.FIRST_COMPLETED,
    )
    for task in pending:
        task.cancel()
    server.close()
    await server.wait_closed()


def main() -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    try:
        asyncio.run(_serve())
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
