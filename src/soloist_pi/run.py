"""Run the Spotify Soloist supervisor."""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from soloist_pi.config import DEFAULT_CONFIG_PATH, ConfigError, load_config
from soloist_pi.supervisor import run_soloist


def build_parser() -> argparse.ArgumentParser:
    """Build the supervisor command parser."""
    parser = argparse.ArgumentParser(
        prog="soloist-pi",
        description="Run the Spotify Soloist supervisor.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help=f"TOML configuration file (default: {DEFAULT_CONFIG_PATH}).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Load configuration and run the supervisor."""
    args = build_parser().parse_args(argv)
    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"soloist-pi: configuration error: {exc}", file=sys.stderr)
        return 2
    return run_soloist(config)


if __name__ == "__main__":
    raise SystemExit(main())
