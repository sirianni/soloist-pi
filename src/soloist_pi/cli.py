"""Command-line entry point for soloist-pi."""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from soloist_pi.config import DEFAULT_CONFIG_PATH, ConfigError, load_config
from soloist_pi.supervisor import run_placeholder


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level command parser."""
    parser = argparse.ArgumentParser(
        prog="soloist-pi",
        description="Manage the Spotify Soloist supervisor.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    run_parser = commands.add_parser("run", help="Run the supervisor and Soloist.")
    run_parser.add_argument(
        "--placeholder",
        action="store_true",
        help="Run the built-in heartbeat process instead of Spotify Soloist.",
    )
    run_parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help=f"TOML configuration file (default: {DEFAULT_CONFIG_PATH}).",
    )
    for name, help_text in (
        ("update", "Fetch and install the current Soloist build."),
        ("ctl", "Send a control command to Soloist."),
    ):
        commands.add_parser(name, help=help_text)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Parse arguments and dispatch the requested command."""
    args = build_parser().parse_args(argv)
    if args.command == "run":
        try:
            load_config(args.config)
        except ConfigError as exc:
            print(f"soloist-pi: configuration error: {exc}", file=sys.stderr)
            return 2
        if not args.placeholder:
            print(
                "soloist-pi: the Soloist backend is not installed yet; "
                "use --placeholder to run the heartbeat process",
                file=sys.stderr,
            )
            return 2
        return run_placeholder()

    print(f"soloist-pi: {args.command} is not implemented yet", file=sys.stderr)
    return 2
