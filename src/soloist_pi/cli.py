"""Command-line entry point for soloist-pi."""

import argparse
from collections.abc import Sequence


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level command parser."""
    parser = argparse.ArgumentParser(
        prog="soloist-pi",
        description="Manage the Spotify Soloist supervisor.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("run", "Run the supervisor and Soloist."),
        ("update", "Fetch and install the current Soloist build."),
        ("ctl", "Send a control command to Soloist."),
    ):
        commands.add_parser(name, help=help_text)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Parse arguments and dispatch the requested command."""
    args = build_parser().parse_args(argv)
    raise SystemExit(f"soloist-pi {args.command}: not implemented yet")
