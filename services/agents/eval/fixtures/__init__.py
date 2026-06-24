"""Eval fixture loader + builder.

The generated ``cases.json`` is the source of truth at runtime;
``build.py`` produces it deterministically from the attack-vector
centroids so the file can be regenerated and diffed in CI.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

FIXTURE_PATH = Path(__file__).parent / "cases.json"


def load_cases() -> dict[str, Any]:
    """Return the parsed fixture: ``{revision, count, schema, cases}``."""
    if not FIXTURE_PATH.exists():
        raise FileNotFoundError(
            f"{FIXTURE_PATH} missing — run `python -m agents.eval.fixtures.build`"
        )
    data = json.loads(FIXTURE_PATH.read_text())
    if data.get("schema") != "volatix.eval.fixture.v1":
        raise ValueError(f"unexpected fixture schema: {data.get('schema')!r}")
    return data
