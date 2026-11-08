"""Tests for the separate supervisor and update commands."""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from soloist_pi.config import DEFAULT_CONFIG_PATH
from soloist_pi.run import build_parser
from soloist_pi.update import main as update_main


def test_run_accepts_config_path() -> None:
    args = build_parser().parse_args(["--config", "/tmp/soloist.toml"])

    assert args.config == Path("/tmp/soloist.toml")


def test_run_uses_default_config_path() -> None:
    args = build_parser().parse_args([])

    assert args.config == DEFAULT_CONFIG_PATH


def test_update_command_forces_download_and_reports_version(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[dict[str, object]] = []

    def update(**kwargs: object) -> bool:
        calls.append(kwargs)
        return True

    monkeypatch.setattr("soloist_pi.update.update_binary", update)
    monkeypatch.setattr(
        "soloist_pi.update.binary_version", lambda path: "soloist 1.2.3"
    )

    assert update_main([]) == 0
    assert calls == [{"force": True}]
    assert (
        capsys.readouterr().out.strip() == "soloist-pi-update: installed soloist 1.2.3"
    )


def test_update_command_reports_failure(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from soloist_pi.updater import UpdateError

    def update(**kwargs: object) -> bool:
        del kwargs
        raise UpdateError("offline")

    monkeypatch.setattr("soloist_pi.update.update_binary", update)

    assert update_main([]) == 1
    assert "soloist-pi-update: update failed: offline" in capsys.readouterr().err


def test_placeholder_runs_and_shuts_down_cleanly() -> None:
    process = subprocess.Popen(
        [sys.executable, "-m", "soloist_pi.placeholder_supervisor"],
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
