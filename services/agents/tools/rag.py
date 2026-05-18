"""Qdrant client (HTTP only, no qdrant-client dep) for the Forensic Investigator.

We talk to Qdrant via plain HTTP/JSON because the agent service has no need
for the streaming gRPC features in the official client. Keeps the runtime
image and the dependency surface tiny.

Endpoint defaults match the Phase 1.2 manifest:
    http://vector-db.default.svc.cluster.local:6333
"""

from __future__ import annotations

import os
from typing import Any

import httpx


DEFAULT_BASE_URL = "http://vector-db.default.svc.cluster.local:6333"
DEFAULT_COLLECTION = "attack_vectors"


class QdrantRag:
    def __init__(self, base_url: str | None = None, collection: str | None = None,
                 timeout: float = 5.0):
        self.base_url = (base_url or os.getenv("QDRANT_URL", DEFAULT_BASE_URL)).rstrip("/")
        self.collection = collection or os.getenv("QDRANT_COLLECTION", DEFAULT_COLLECTION)
        self.timeout = timeout
        self._client = httpx.Client(timeout=timeout)

    # --- lifecycle ------------------------------------------------------

    def close(self) -> None:
        self._client.close()

    # --- admin ----------------------------------------------------------

    def ensure_collection(self, vector_size: int, distance: str = "Cosine") -> None:
        """Idempotent. Creates the collection if it isn't there yet."""
        resp = self._client.get(f"{self.base_url}/collections/{self.collection}")
        if resp.status_code == 200:
            return
        body = {"vectors": {"size": vector_size, "distance": distance}}
        put = self._client.put(f"{self.base_url}/collections/{self.collection}", json=body)
        put.raise_for_status()

    def upsert(self, points: list[dict[str, Any]]) -> None:
        body = {"points": points}
        resp = self._client.put(
            f"{self.base_url}/collections/{self.collection}/points",
            json=body,
            params={"wait": "true"},
        )
        resp.raise_for_status()

    # --- query ----------------------------------------------------------

    def search(self, vector: list[float], limit: int = 3) -> list[dict[str, Any]]:
        body = {"vector": vector, "limit": limit, "with_payload": True}
        resp = self._client.post(
            f"{self.base_url}/collections/{self.collection}/points/search",
            json=body,
        )
        resp.raise_for_status()
        return resp.json().get("result", []) or []
