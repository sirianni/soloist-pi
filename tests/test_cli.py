"""Smoke tests for the initial command-line scaffold."""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from soloist_pi.cli import build_parser, main
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


def test_update_command_forces_download_and_reports_version(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[dict[str, object]] = []

    def update(**kwargs: object) -> bool:
        calls.append(kwargs)
        return True

    monkeypatch.setattr("soloist_pi.cli.update_binary", update)
    monkeypatch.setattr("soloist_pi.cli.binary_version", lambda path: "soloist 1.2.3")

    assert main(["update"]) == 0
    assert calls == [{"force": True}]
    assert capsys.readouterr().out.strip() == "soloist-pi: installed soloist 1.2.3"


def test_update_command_reports_failure(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from soloist_pi.updater import UpdateError

    def update(**kwargs: object) -> bool:
        del kwargs
        raise UpdateError("offline")

    monkeypatch.setattr("soloist_pi.cli.update_binary", update)

    assert main(["update"]) == 1
    assert "soloist-pi: update failed: offline" in capsys.readouterr().err


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
