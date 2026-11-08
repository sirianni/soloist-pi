"""Fetch and install the current Spotify Soloist build."""

import argparse
import sys
from collections.abc import Sequence

from soloist_pi.updater import (
    DEFAULT_BINARY_PATH,
    UpdateError,
    binary_version,
    update_binary,
)


def main(argv: Sequence[str] | None = None) -> int:
    """Force a Soloist update and report the installed version."""
    argparse.ArgumentParser(
        prog="soloist-pi-update",
        description="Force-download and install the current Soloist build.",
    ).parse_args(argv)

    try:
        update_binary(force=True)
    except UpdateError as exc:
        print(f"soloist-pi-update: update failed: {exc}", file=sys.stderr)
        return 1

    version = binary_version(DEFAULT_BINARY_PATH)
    if version is None:
        print(
            "soloist-pi-update: update completed but the installed binary is unusable",
            file=sys.stderr,
        )
        return 1
    print(f"soloist-pi-update: installed {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
