"""Small process supervisor used by the temporary Soloist placeholder."""

from __future__ import annotations

import signal
import subprocess
import sys
import threading

SHUTDOWN_TIMEOUT_SECONDS = 10


def run_placeholder() -> int:
    """Run the packaged heartbeat child and forward service shutdown signals."""
    child = subprocess.Popen(
        [sys.executable, "-u", "-m", "soloist_pi.placeholder"],
        # Inherit stdout/stderr so systemd captures child output in its journal.
    )
    stop_requested = threading.Event()
    previous_handlers: dict[int, signal.Handlers] = {}

    def request_stop(signum: int, frame: object) -> None:
        del signum, frame
        stop_requested.set()

    for signum in (signal.SIGTERM, signal.SIGINT):
        previous_handlers[signum] = signal.signal(signum, request_stop)

    try:
        while True:
            try:
                exit_status = child.wait(timeout=0.2)
            except subprocess.TimeoutExpired:
                if not stop_requested.is_set():
                    continue
                print("soloist-pi: forwarding shutdown to placeholder", flush=True)
                child.terminate()
                try:
                    child.wait(timeout=SHUTDOWN_TIMEOUT_SECONDS)
                except subprocess.TimeoutExpired:
                    print(
                        "soloist-pi: placeholder did not stop; sending SIGKILL",
                        flush=True,
                    )
                    child.kill()
                    child.wait()
                return 0
            else:
                return exit_status
    finally:
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)
