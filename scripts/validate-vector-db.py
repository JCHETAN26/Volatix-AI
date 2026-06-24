#!/usr/bin/env python3
"""Volatix-AI — Vector DB validation (Phase 1 / Task 1.2 acceptance).

Pure-stdlib script. Hits a Qdrant instance and proves:
  1. /healthz responds 200 OK.
  2. A test collection can be created.
  3. The collection is visible via GET.
  4. The collection can be torn down cleanly.

Run after `make infra-up` and `make port-forward-vector`, e.g.:
    python3 scripts/validate-vector-db.py
or against an explicit host:
    python3 scripts/validate-vector-db.py --base-url http://localhost:6333
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
import uuid
from typing import Any


DEFAULT_BASE_URL = "http://localhost:6333"
DEFAULT_VECTOR_SIZE = 8
DEFAULT_TIMEOUT = 5.0


def _request(method: str, url: str, *, body: dict[str, Any] | None = None,
             timeout: float = DEFAULT_TIMEOUT) -> tuple[int, dict[str, Any] | None]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url=url, method=method, data=data)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, _safe_json(exc.read())
    return status, _safe_json(raw)


def _safe_json(raw: bytes) -> dict[str, Any] | None:
    if not raw:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def check_health(base_url: str) -> None:
    status, _ = _request("GET", f"{base_url}/healthz")
    if status != 200:
        raise SystemExit(f"healthz returned {status}, expected 200")
    print(f"  ✓ GET /healthz → {status}")


def create_collection(base_url: str, name: str, vector_size: int) -> None:
    body = {"vectors": {"size": vector_size, "distance": "Cosine"}}
    status, payload = _request("PUT", f"{base_url}/collections/{name}", body=body)
    if status not in (200, 201):
        raise SystemExit(f"create collection failed: status={status} payload={payload}")
    print(f"  ✓ PUT /collections/{name} → {status}")


def get_collection(base_url: str, name: str) -> None:
    status, payload = _request("GET", f"{base_url}/collections/{name}")
    if status != 200:
        raise SystemExit(f"get collection failed: status={status} payload={payload}")
    result = (payload or {}).get("result") or {}
    config = result.get("config", {}).get("params", {}).get("vectors", {})
    size = config.get("size", "?")
    distance = config.get("distance", "?")
    print(f"  ✓ GET /collections/{name} → status=200  size={size} distance={distance}")


def delete_collection(base_url: str, name: str) -> None:
    status, payload = _request("DELETE", f"{base_url}/collections/{name}")
    if status != 200:
        raise SystemExit(f"delete collection failed: status={status} payload={payload}")
    print(f"  ✓ DELETE /collections/{name} → {status}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL,
                        help=f"Qdrant base URL (default: {DEFAULT_BASE_URL})")
    parser.add_argument("--vector-size", type=int, default=DEFAULT_VECTOR_SIZE,
                        help=f"Test collection vector size (default: {DEFAULT_VECTOR_SIZE})")
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    collection = f"volatix-validation-{uuid.uuid4().hex[:8]}"

    print(f"Validating vector DB at {base}")
    try:
        check_health(base)
        create_collection(base, collection, args.vector_size)
        get_collection(base, collection)
        delete_collection(base, collection)
    except urllib.error.URLError as exc:
        print(f"  ✗ network error: {exc}", file=sys.stderr)
        return 1

    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
