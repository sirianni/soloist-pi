"""Tests for the systemd PipeWire readiness helper."""

import subprocess

import pytest

from soloist_pi.pipewire_ready import main, wait_for_default_sink


def test_wait_for_default_sink_probes_wireplumber(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []

    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr("soloist_pi.pipewire_ready.subprocess.run", run)

    assert wait_for_default_sink(timeout_seconds=1, wpctl_path="/tmp/wpctl")
    assert len(calls) == 1
    command, options = calls[0]
    assert command == ["/tmp/wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"]
    assert options["check"] is True
    assert options["stdout"] == subprocess.DEVNULL
    assert options["stderr"] == subprocess.DEVNULL
    assert isinstance(options["timeout"], float)
    assert 0 < options["timeout"] <= 1


def test_wait_for_default_sink_retries_until_sink_is_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0

    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise subprocess.CalledProcessError(1, command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr("soloist_pi.pipewire_ready.subprocess.run", run)
    monkeypatch.setattr("soloist_pi.pipewire_ready.time.sleep", lambda _: None)

    assert wait_for_default_sink(timeout_seconds=1, poll_interval_seconds=0.001)
    assert attempts == 2


def test_wait_for_default_sink_times_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0

    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal attempts
        attempts += 1
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr("soloist_pi.pipewire_ready.subprocess.run", run)

    assert not wait_for_default_sink(timeout_seconds=0.01, poll_interval_seconds=0.001)
    assert attempts > 0


def test_readiness_cli_reports_timeout(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        "soloist_pi.pipewire_ready.wait_for_default_sink", lambda **_: False
    )

    assert main(["--timeout", "0.5"]) == 1
    assert (
        capsys.readouterr().err.strip()
        == "soloist-pi: PipeWire default sink did not become ready within 0.5 seconds"
    )


def test_wait_for_default_sink_rejects_nonpositive_timeout() -> None:
    with pytest.raises(ValueError, match="timeout_seconds"):
        wait_for_default_sink(timeout_seconds=0)
