"""Temporary heartbeat process standing in for the Soloist executable."""

from __future__ import annotations

import signal
import threading
from datetime import UTC, datetime

HEARTBEAT_INTERVAL_SECONDS = 30


def main() -> int:
    """Print a startup message and a timestamped heartbeat every 30 seconds."""
    stop_requested = threading.Event()

    def request_stop(signum: int, frame: object) -> None:
        del signum, frame
        stop_requested.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    while not stop_requested.is_set():
        now = datetime.now(UTC).isoformat(timespec="seconds")
        print(f"placeholder-soloist: heartbeat {now}", flush=True)
        if stop_requested.wait(HEARTBEAT_INTERVAL_SECONDS):
            break
    print("placeholder-soloist: stopped", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
