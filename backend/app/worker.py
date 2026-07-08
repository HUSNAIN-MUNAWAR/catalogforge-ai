"""Background worker boundary for CatalogForge jobs.

The demo API executes deterministic processing synchronously so it remains self-contained.
In Docker this worker is a separate process ready to claim queued work once a Redis-backed
queue implementation is configured.
"""
from __future__ import annotations

import time

from .seed import seed


def main() -> None:
    seed()
    print("CatalogForge worker ready: deterministic local queue boundary active.", flush=True)
    while True:
        time.sleep(30)


if __name__ == "__main__":
    main()
