"""Wait for a usable native PipeWire default output sink."""

from __future__ import annotations

import argparse
import math
import subprocess
import sys
import time
from collections.abc import Sequence

DEFAULT_TIMEOUT_SECONDS = 60.0
DEFAULT_POLL_INTERVAL_SECONDS = 1.0
PROBE_TIMEOUT_SECONDS = 2.0
DEFAULT_WPCTL_PATH = "/usr/bin/wpctl"


def wait_for_default_sink(
    *,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
    wpctl_path: str = DEFAULT_WPCTL_PATH,
) -> bool:
    """Return once wpctl can query WirePlumber's default audio sink."""
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be a finite positive number")
    if not math.isfinite(poll_interval_seconds) or poll_interval_seconds <= 0:
        raise ValueError("poll_interval_seconds must be a finite positive number")

    deadline = time.monotonic() + timeout_seconds
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False

        if _probe_default_sink(wpctl_path, min(PROBE_TIMEOUT_SECONDS, remaining)):
            return True

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        time.sleep(min(poll_interval_seconds, remaining))


def _probe_default_sink(wpctl_path: str, timeout_seconds: float) -> bool:
    try:
        subprocess.run(
            [wpctl_path, "get-volume", "@DEFAULT_AUDIO_SINK@"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return True


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point for the systemd startup readiness check."""
    parser = argparse.ArgumentParser(
        description="Wait for a usable PipeWire default audio sink."
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="maximum wait in seconds (default: %(default)s)",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=DEFAULT_POLL_INTERVAL_SECONDS,
        help="seconds between probes (default: %(default)s)",
    )
    parser.add_argument(
        "--wpctl",
        default=DEFAULT_WPCTL_PATH,
        help="path to wpctl (default: %(default)s)",
    )
    args = parser.parse_args(argv)

    try:
        ready = wait_for_default_sink(
            timeout_seconds=args.timeout,
            poll_interval_seconds=args.poll_interval,
            wpctl_path=args.wpctl,
        )
    except ValueError as exc:
        parser.error(str(exc))

    if ready:
        return 0

    print(
        "soloist-pi: PipeWire default sink did not become ready "
        f"within {args.timeout:g} seconds",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
