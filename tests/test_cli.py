"""Smoke tests for the initial command-line scaffold."""

import pytest

from soloist_pi.cli import build_parser


@pytest.mark.parametrize("command", ("run", "update", "ctl"))
def test_planned_commands_are_registered(command: str) -> None:
    args = build_parser().parse_args([command])

    assert args.command == command
