"""Supervise the managed Soloist executable and forward service shutdown."""

from __future__ import annotations

import signal
import subprocess
import sys
import threading
import time
from collections.abc import Sequence
from pathlib import Path

from soloist_pi.config import Config
from soloist_pi.updater import (
    DEFAULT_BINARY_PATH,
    DEFAULT_METADATA_PATH,
    DEFAULT_RELEASE_URL,
    UpdateError,
    is_usable_binary,
    update_binary,
)

SHUTDOWN_TIMEOUT_SECONDS = 10
MEANINGFUL_RUN_SECONDS = 300
MAX_IMMEDIATE_EXPIRY_RETRIES = 3


def run_placeholder() -> int:
    """Run the packaged heartbeat child and forward service shutdown signals."""
    return _run_child(
        [sys.executable, "-u", "-m", "soloist_pi.placeholder"], "placeholder"
    )[0]


def run_soloist(
    config: Config,
    *,
    binary_path: Path | str = DEFAULT_BINARY_PATH,
    metadata_path: Path | str = DEFAULT_METADATA_PATH,
    release_url: str = DEFAULT_RELEASE_URL,
) -> int:
    """Refresh at startup, run Soloist, and force-refresh on status 10."""
    managed_binary = Path(binary_path)
    try:
        update_binary(
            binary_path=managed_binary,
            metadata_path=metadata_path,
            release_url=release_url,
        )
    except UpdateError as exc:
        if not is_usable_binary(managed_binary):
            print(
                "soloist-pi: cannot update Soloist and no usable installed binary "
                f"exists: {exc}",
                file=sys.stderr,
            )
            return 1
        print(
            "soloist-pi: update check failed; continuing with the installed "
            f"Soloist binary: {exc}",
            file=sys.stderr,
            flush=True,
        )

    if not is_usable_binary(managed_binary):
        print(
            f"soloist-pi: managed Soloist binary is not usable: {managed_binary}",
            file=sys.stderr,
        )
        return 1

    arguments = [str(managed_binary), *config.soloist_arguments()]
    immediate_expiry_retries = 0
    while True:
        status, run_seconds, stopped = _run_child(arguments, "Soloist")
        if stopped or status != 10:
            return status

        if run_seconds >= MEANINGFUL_RUN_SECONDS:
            immediate_expiry_retries = 0
        if immediate_expiry_retries >= MAX_IMMEDIATE_EXPIRY_RETRIES:
            print(
                "soloist-pi: Soloist repeatedly exited with status 10; "
                "stopping the supervisor to avoid a restart loop",
                file=sys.stderr,
                flush=True,
            )
            return 0

        immediate_expiry_retries += 1
        print(
            "soloist-pi: Soloist exited with status 10; forcing a fresh download",
            flush=True,
        )
        try:
            update_binary(
                binary_path=managed_binary,
                metadata_path=metadata_path,
                release_url=release_url,
                force=True,
            )
        except UpdateError as exc:
            print(
                f"soloist-pi: forced Soloist refresh failed; stopping: {exc}",
                file=sys.stderr,
                flush=True,
            )
            return 0


def _run_child(command: Sequence[str], name: str) -> tuple[int, float, bool]:
    """Run one child process, forwarding shutdown and enforcing its grace period."""
    stop_requested = threading.Event()
    previous_handlers: dict[int, signal.Handlers] = {}

    def request_stop(signum: int, frame: object) -> None:
        del signum, frame
        stop_requested.set()

    for signum in (signal.SIGTERM, signal.SIGINT):
        previous_handlers[signum] = signal.signal(signum, request_stop)

    started_at = time.monotonic()
    try:
        try:
            child = subprocess.Popen(command)
        except OSError as exc:
            print(f"soloist-pi: cannot start {name}: {exc}", file=sys.stderr)
            return 1, 0.0, False

        while True:
            try:
                exit_status = child.wait(timeout=0.2)
            except subprocess.TimeoutExpired:
                if not stop_requested.is_set():
                    continue
                print(f"soloist-pi: forwarding shutdown to {name}", flush=True)
                try:
                    child.send_signal(signal.SIGTERM)
                except ProcessLookupError:
                    return child.wait(), time.monotonic() - started_at, False
                try:
                    child.wait(timeout=SHUTDOWN_TIMEOUT_SECONDS)
                except subprocess.TimeoutExpired:
                    print(
                        f"soloist-pi: {name} did not stop; sending SIGKILL",
                        flush=True,
                    )
                    child.kill()
                    child.wait()
                return 0, time.monotonic() - started_at, True
            else:
                return exit_status, time.monotonic() - started_at, False
    finally:
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)
