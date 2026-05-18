"""Entrypoint for the agents container."""

from __future__ import annotations

import sys

from .consumer import main


if __name__ == "__main__":
    sys.exit(main())
