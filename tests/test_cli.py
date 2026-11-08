"""Smoke tests for the initial command-line scaffold."""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from soloist_pi.cli import build_parser
from soloist_pi.config import DEFAULT_CONFIG_PATH


@pytest.mark.parametrize("command", ("run", "update", "ctl"))
def test_planned_commands_are_registered(command: str) -> None:
    args = build_parser().parse_args([command])

    assert args.command == command


def test_run_accepts_config_path() -> None:
    args = build_parser().parse_args(["run", "--config", "/tmp/soloist.toml"])

    assert args.config == Path("/tmp/soloist.toml")


def test_run_uses_default_config_path() -> None:
    args = build_parser().parse_args(["run"])

    assert args.config == DEFAULT_CONFIG_PATH


def test_placeholder_runs_and_shuts_down_cleanly(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        'device_name = "Test Device"\n'
        'api_key = "test-secret"\n'
        'data_dir = "/tmp/soloist-state"\n'
        'cache_dir = "/tmp/soloist-cache"\n',
        encoding="utf-8",
    )
    config_path.chmod(0o600)

    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "soloist_pi",
            "run",
            "--config",
            str(config_path),
            "--placeholder",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        time.sleep(0.2)
        os.kill(process.pid, signal.SIGTERM)
        output, _ = process.communicate(timeout=5)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()

    assert process.returncode == 0
    assert "placeholder-soloist: heartbeat" in output
    assert "soloist-pi: forwarding shutdown" in output
    assert "placeholder-soloist: stopped" in output
    assert "test-secret" not in output
