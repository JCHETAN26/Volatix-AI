"""Entrypoint for the classifier service container."""

from __future__ import annotations

import logging
import signal
import sys

from .consumer import ClassifierService, Config


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    cfg = Config.from_env()
    service = ClassifierService(cfg)

    signal.signal(signal.SIGINT, service.shutdown)
    signal.signal(signal.SIGTERM, service.shutdown)

    return service.run()


if __name__ == "__main__":
    sys.exit(main())
