"""Tests for the Soloist service process and expiry retry policy."""

from pathlib import Path
from typing import Any

from soloist_pi import supervisor
from soloist_pi.config import Config
from soloist_pi.updater import UpdateError


def test_runs_soloist_with_validated_config_arguments(monkeypatch: Any) -> None:
    config = Config(
        device_name="Kitchen",
        api_key="private-test-key",
        data_dir=Path("/tmp/soloist-state"),
        cache_dir=Path("/tmp/soloist-cache"),
        initial_volume=35,
    )
    update_calls: list[dict[str, object]] = []
    child_commands: list[list[str]] = []

    def update(**kwargs: object) -> bool:
        update_calls.append(kwargs)
        return False

    def run_child(command: list[str], name: str) -> tuple[int, float, bool]:
        child_commands.append(command)
        assert name == "Soloist"
        return 7, 1.0, False

    monkeypatch.setattr(supervisor, "update_binary", update)
    monkeypatch.setattr(supervisor, "is_usable_binary", lambda path: True)
    monkeypatch.setattr(supervisor, "_run_child", run_child)

    status = supervisor.run_soloist(
        config,
        binary_path="/tmp/managed/soloist",
        metadata_path="/tmp/managed/release.json",
        release_url="http://127.0.0.1/release.tar.gz",
    )

    assert status == 7
    assert update_calls == [
        {
            "binary_path": Path("/tmp/managed/soloist"),
            "metadata_path": "/tmp/managed/release.json",
            "release_url": "http://127.0.0.1/release.tar.gz",
        }
    ]
    assert child_commands == [
        [
            "/tmp/managed/soloist",
            "--device-name",
            "Kitchen",
            "--api-key",
            "private-test-key",
            "--data-dir",
            "/tmp/soloist-state",
            "--cache-dir",
            "/tmp/soloist-cache",
            "--initial-volume",
            "35",
        ]
    ]


def test_update_failure_falls_back_to_usable_binary_without_logging_key(
    monkeypatch: Any, capsys: Any
) -> None:
    config = Config(
        device_name="Kitchen",
        api_key="private-test-key",
        data_dir=Path("/tmp/state"),
        cache_dir=Path("/tmp/cache"),
    )
    child_commands: list[list[str]] = []

    def fail_update(**kwargs: object) -> bool:
        del kwargs
        raise UpdateError("local CDN unavailable")

    monkeypatch.setattr(supervisor, "update_binary", fail_update)
    monkeypatch.setattr(supervisor, "is_usable_binary", lambda path: True)
    monkeypatch.setattr(
        supervisor,
        "_run_child",
        lambda command, name: (0, child_commands.append(list(command)) or 1.0, False),
    )

    assert supervisor.run_soloist(config, binary_path="/tmp/soloist") == 0
    assert child_commands
    output = capsys.readouterr()
    assert "continuing with the installed Soloist binary" in output.err
    assert "private-test-key" not in output.err


def test_startup_fails_clearly_without_usable_binary(
    monkeypatch: Any, capsys: Any
) -> None:
    config = Config(
        device_name="Kitchen",
        api_key="private-test-key",
        data_dir=Path("/tmp/state"),
        cache_dir=Path("/tmp/cache"),
    )

    def fail_update(**kwargs: object) -> bool:
        del kwargs
        raise UpdateError("local CDN unavailable")

    monkeypatch.setattr(supervisor, "update_binary", fail_update)
    monkeypatch.setattr(supervisor, "is_usable_binary", lambda path: False)
    monkeypatch.setattr(
        supervisor,
        "_run_child",
        lambda command, name: (_ for _ in ()).throw(AssertionError("must not run")),
    )

    assert supervisor.run_soloist(config, binary_path="/tmp/missing") == 1
    output = capsys.readouterr()
    assert "no usable installed binary exists" in output.err
    assert "local CDN unavailable" in output.err
    assert "private-test-key" not in output.err


def test_status_10_forces_a_bounded_refresh_after_startup(monkeypatch: Any) -> None:
    config = Config(
        device_name="Kitchen",
        api_key="private-test-key",
        data_dir=Path("/tmp/state"),
        cache_dir=Path("/tmp/cache"),
    )
    update_calls: list[dict[str, object]] = []
    child_statuses = iter([(10, 1.0, False)] * 4)

    def update(**kwargs: object) -> bool:
        update_calls.append(kwargs)
        return True

    monkeypatch.setattr(supervisor, "update_binary", update)
    monkeypatch.setattr(supervisor, "is_usable_binary", lambda path: True)
    monkeypatch.setattr(
        supervisor, "_run_child", lambda command, name: next(child_statuses)
    )

    assert supervisor.run_soloist(config, binary_path="/tmp/soloist") == 0
    assert [call.get("force", False) for call in update_calls] == [
        False,
        True,
        True,
        True,
    ]


def test_failed_forced_refresh_stops_instead_of_triggering_service_restart(
    monkeypatch: Any, capsys: Any
) -> None:
    config = Config(
        device_name="Kitchen",
        api_key="private-test-key",
        data_dir=Path("/tmp/state"),
        cache_dir=Path("/tmp/cache"),
    )
    update_calls: list[dict[str, object]] = []

    def update(**kwargs: object) -> bool:
        update_calls.append(kwargs)
        if kwargs.get("force") is True:
            raise UpdateError("CDN unavailable")
        return False

    monkeypatch.setattr(supervisor, "update_binary", update)
    monkeypatch.setattr(supervisor, "is_usable_binary", lambda path: True)
    monkeypatch.setattr(
        supervisor, "_run_child", lambda command, name: (10, 1.0, False)
    )

    assert supervisor.run_soloist(config, binary_path="/tmp/soloist") == 0
    assert [call.get("force", False) for call in update_calls] == [False, True]
    assert "forced Soloist refresh failed; stopping" in capsys.readouterr().err


def test_meaningful_run_resets_the_immediate_expiry_retry_limit(
    monkeypatch: Any,
) -> None:
    config = Config(
        device_name="Kitchen",
        api_key="private-test-key",
        data_dir=Path("/tmp/state"),
        cache_dir=Path("/tmp/cache"),
    )
    update_calls: list[dict[str, object]] = []
    child_statuses = iter(
        [
            (10, 1.0, False),
            (10, supervisor.MEANINGFUL_RUN_SECONDS, False),
            (10, 1.0, False),
            (10, 1.0, False),
            (10, 1.0, False),
            (10, 1.0, False),
        ]
    )

    def update(**kwargs: object) -> bool:
        update_calls.append(kwargs)
        return True

    monkeypatch.setattr(supervisor, "update_binary", update)
    monkeypatch.setattr(supervisor, "is_usable_binary", lambda path: True)
    monkeypatch.setattr(
        supervisor, "_run_child", lambda command, name: next(child_statuses)
    )

    assert supervisor.run_soloist(config, binary_path="/tmp/soloist") == 0
    assert sum(call.get("force", False) is True for call in update_calls) == 4
