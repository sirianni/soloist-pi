"""Tests for private configuration loading and Soloist argument construction."""

from pathlib import Path

import pytest

from soloist_pi.config import ConfigError, load_config


def write_config(
    tmp_path: Path,
    body: str,
    *,
    config_mode: int = 0o600,
) -> Path:
    config_path = tmp_path / "config.toml"
    config_path.write_text(body, encoding="utf-8")
    config_path.chmod(config_mode)
    return config_path


def minimal_config() -> str:
    return """
device_name = "Living Room"
api_key = "secret-key"
data_dir = "/var/lib/soloist/state/soloist"
cache_dir = "/var/cache/soloist"
"""


def test_load_config_and_construct_minimal_arguments(tmp_path: Path) -> None:
    config_path = write_config(tmp_path, minimal_config())

    config = load_config(config_path)

    assert config.device_name == "Living Room"
    assert config.api_key == "secret-key"
    assert "secret-key" not in repr(config)
    assert config.soloist_arguments() == [
        "--device-name",
        "Living Room",
        "--api-key",
        "secret-key",
        "--data-dir",
        "/var/lib/soloist/state/soloist",
        "--cache-dir",
        "/var/cache/soloist",
    ]


def test_load_all_optional_settings(tmp_path: Path) -> None:
    body = (
        minimal_config()
        + """
cache_size_mb = 250
pipewire_device = "alsa_output.platform-sound.analog-stereo"
initial_volume = 42
websocket_address = "127.0.0.1:9000"
"""
    )
    config = load_config(write_config(tmp_path, body))

    assert config.soloist_arguments() == [
        "--device-name",
        "Living Room",
        "--api-key",
        "secret-key",
        "--data-dir",
        "/var/lib/soloist/state/soloist",
        "--cache-dir",
        "/var/cache/soloist",
        "--cache-size",
        "250",
        "--pipewire-device",
        "alsa_output.platform-sound.analog-stereo",
        "--initial-volume",
        "42",
        "--ws",
        "127.0.0.1:9000",
    ]


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("device_name", '""', "device_name"),
        ("data_dir", '"relative"', "data_dir"),
        ("cache_dir", '"/var/lib/soloist/state/soloist"', "different paths"),
        ("cache_size_mb", "1", "at least 100"),
        ("cache_size_mb", "true", "integer"),
        ("initial_volume", "101", "between 0 and 100"),
        ("websocket_address", '"0.0.0.0:9000"', "loopback"),
        ("extra", '"unexpected"', "unknown configuration"),
    ],
)
def test_reject_invalid_settings(
    tmp_path: Path, field: str, value: str, error: str
) -> None:
    body = minimal_config()
    if field in {"device_name", "data_dir", "cache_dir"}:
        original = {
            "device_name": 'device_name = "Living Room"',
            "data_dir": 'data_dir = "/var/lib/soloist/state/soloist"',
            "cache_dir": 'cache_dir = "/var/cache/soloist"',
        }[field]
        body = body.replace(original, f"{field} = {value}")
    else:
        body += f"{field} = {value}\n"

    with pytest.raises(ConfigError, match=error):
        load_config(write_config(tmp_path, body))


@pytest.mark.parametrize("address", ["localhost:0", "[::1]:3210"])
def test_allow_loopback_websocket_addresses(tmp_path: Path, address: str) -> None:
    body = minimal_config() + f'websocket_address = "{address}"\n'

    assert load_config(write_config(tmp_path, body)).websocket_address == address


@pytest.mark.parametrize(
    "value",
    [
        '""',
        '"two words"',
        '"secret\\nkey"',
        '"secret\\u0000key"',
        "42",
        "true",
    ],
)
def test_reject_invalid_api_key(tmp_path: Path, value: str) -> None:
    body = minimal_config().replace('api_key = "secret-key"', f"api_key = {value}")

    with pytest.raises(ConfigError, match="api_key"):
        load_config(write_config(tmp_path, body))


def test_reject_non_private_configuration_file(tmp_path: Path) -> None:
    config_path = write_config(tmp_path, minimal_config(), config_mode=0o644)

    with pytest.raises(ConfigError, match="configuration file.*group or others"):
        load_config(config_path)


def test_reject_configuration_symlink(tmp_path: Path) -> None:
    config_path = write_config(tmp_path, minimal_config())
    config_link = tmp_path / "config-link.toml"
    config_link.symlink_to(config_path)

    with pytest.raises(ConfigError, match="cannot open configuration file"):
        load_config(config_link)
