"""Seed Qdrant `attack_vectors` with synthetic exploit signatures (Phase 4.2).

Each point is a 5-dimensional feature vector matching the engine's
FeatureFrame order:

    [ofi, realized_vol, mid_price, total_volume, window_count]

Plus a payload describing the attack class. The Forensic Investigator
searches with the live case's feature_vector() and surfaces the top-K
nearest matches.

Idempotent — re-running just overwrites the same point IDs.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow `python services/agents/seed_vector_db.py` from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.tools.rag import QdrantRag


# Each entry: (id, name, severity, [ofi, rv, mid, vol, win], notes)
SEED_POINTS = [
    (
        1,
        "Flash-Loan Imbalance (long side)",
        0.95,
        [9500.0, 0.045, 192.0, 65000.0, 120],
        "Large positive OFI plus elevated realized vol — classic flash-loan pump.",
    ),
    (
        2,
        "Flash-Loan Imbalance (short side)",
        0.95,
        [-9500.0, 0.045, 192.0, 65000.0, 120],
        "Large negative OFI plus elevated realized vol — short-side flash loan.",
    ),
    (
        3,
        "Wash-Trading Pattern",
        0.7,
        [200.0, 0.005, 190.0, 80000.0, 60],
        "Near-zero OFI but elevated volume — typical of wash trades.",
    ),
    (
        4,
        "Pump-and-Dump Spike",
        0.9,
        [5500.0, 0.07, 210.0, 45000.0, 110],
        "Mid-price shifted away from baseline with high vol + positive OFI.",
    ),
    (
        5,
        "Stop-Hunt Sweep",
        0.85,
        [-6000.0, 0.055, 187.0, 50000.0, 100],
        "Sharp negative OFI sweep into liquidity below market.",
    ),
    (
        6,
        "Quote Stuffing",
        0.6,
        [50.0, 0.001, 190.0, 5000.0, 128],
        "Low OFI, low vol, very high window_count — burst of cancels.",
    ),
    (
        7,
        "Spoofing — Bid",
        0.8,
        [-3200.0, 0.02, 191.0, 30000.0, 90],
        "Negative OFI with moderate vol; bid layer pulled before fill.",
    ),
    (
        8,
        "Spoofing — Ask",
        0.8,
        [3200.0, 0.02, 191.0, 30000.0, 90],
        "Positive OFI with moderate vol; ask layer pulled before fill.",
    ),
    (
        9,
        "Cross-Venue Arbitrage Surge",
        0.4,
        [1000.0, 0.012, 192.5, 12000.0, 80],
        "Mildly directional OFI with moderate vol — benign arb signature.",
    ),
    (
        10,
        "Earnings-Reaction Burst",
        0.3,
        [400.0, 0.018, 188.0, 20000.0, 90],
        "Moderate OFI + vol around scheduled earnings; usually benign.",
    ),
]


def build_points():
    points = []
    for pid, name, severity, vec, notes in SEED_POINTS:
        points.append({
            "id": pid,
            "vector": vec,
            "payload": {
                "attack_id": f"av-{pid:03d}",
                "name": name,
                "severity": severity,
                "notes": notes,
            },
        })
    return points


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=None, help="Qdrant base URL")
    parser.add_argument("--collection", default=None)
    args = parser.parse_args(argv)

    rag = QdrantRag(base_url=args.url, collection=args.collection)
    points = build_points()
    rag.ensure_collection(vector_size=len(points[0]["vector"]))
    rag.upsert(points)
    print(f"seeded {len(points)} attack vectors into "
          f"{rag.base_url}/collections/{rag.collection}")
    rag.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
