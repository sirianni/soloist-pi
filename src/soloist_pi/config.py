"""Load and validate the supervisor-owned Soloist configuration."""

from __future__ import annotations

import ipaddress
import os
import stat
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

DEFAULT_CONFIG_PATH = Path("/var/lib/soloist/config/config.toml")


class ConfigError(ValueError):
    """Raised when the private configuration is invalid."""


@dataclass(frozen=True)
class Config:
    """Validated Soloist settings with the API key excluded from repr."""

    device_name: str
    api_key: str = field(repr=False)
    data_dir: Path
    cache_dir: Path
    cache_size_mb: int | None = None
    pipewire_device: str | None = None
    initial_volume: int | None = None
    websocket_address: str | None = None

    def soloist_arguments(self) -> list[str]:
        """Return Soloist's documented flags without logging secret values."""
        arguments = [
            "--device-name",
            self.device_name,
            "--api-key",
            self.api_key,
            "--data-dir",
            str(self.data_dir),
            "--cache-dir",
            str(self.cache_dir),
        ]
        if self.cache_size_mb is not None:
            arguments.extend(("--cache-size", str(self.cache_size_mb)))
        if self.pipewire_device is not None:
            arguments.extend(("--pipewire-device", self.pipewire_device))
        if self.initial_volume is not None:
            arguments.extend(("--initial-volume", str(self.initial_volume)))
        if self.websocket_address is not None:
            arguments.extend(("--ws", self.websocket_address))
        return arguments


def load_config(path: Path | str = DEFAULT_CONFIG_PATH) -> Config:
    """Read and validate the private TOML configuration."""
    config_path = Path(path)
    document = _read_private_file(config_path, "configuration file")
    try:
        values = tomllib.loads(document.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"invalid TOML configuration in {config_path}") from exc

    if not isinstance(values, dict):  # Defensive; TOML's top level is a table.
        raise ConfigError("configuration must be a TOML table")

    allowed = {
        "device_name",
        "api_key",
        "data_dir",
        "cache_dir",
        "cache_size_mb",
        "pipewire_device",
        "initial_volume",
        "websocket_address",
    }
    unknown = sorted(values.keys() - allowed)
    if unknown:
        raise ConfigError(f"unknown configuration setting(s): {', '.join(unknown)}")

    device_name = _required_string(values, "device_name")
    if not device_name.strip() or any(ord(character) < 32 for character in device_name):
        raise ConfigError(
            "device_name must be non-empty and contain no control characters"
        )

    api_key = _required_api_key(values)

    data_dir = _required_path(values, "data_dir")
    cache_dir = _required_path(values, "cache_dir")
    if data_dir == cache_dir:
        raise ConfigError("data_dir and cache_dir must be different paths")

    cache_size_mb = _optional_integer(values, "cache_size_mb")
    if cache_size_mb is not None and cache_size_mb != 0 and cache_size_mb < 100:
        raise ConfigError("cache_size_mb must be 0 or at least 100")

    pipewire_device = _optional_string(values, "pipewire_device")
    initial_volume = _optional_integer(values, "initial_volume")
    if initial_volume is not None and not 0 <= initial_volume <= 100:
        raise ConfigError("initial_volume must be between 0 and 100")

    websocket_address = _optional_string(values, "websocket_address")
    if websocket_address is not None:
        _validate_websocket_address(websocket_address)

    return Config(
        device_name=device_name,
        api_key=api_key,
        data_dir=data_dir,
        cache_dir=cache_dir,
        cache_size_mb=cache_size_mb,
        pipewire_device=pipewire_device,
        initial_volume=initial_volume,
        websocket_address=websocket_address,
    )


def _read_private_file(path: Path, description: str) -> bytes:
    """Open a regular file without following symlinks and require mode 0600-ish."""
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ConfigError(f"cannot open {description} {path}: {exc.strerror}") from exc

    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise ConfigError(f"{description} {path} must be a regular file")
        if info.st_mode & 0o077:
            raise ConfigError(
                f"{description} {path} must not be accessible by group or others"
            )
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = -1
            return stream.read()
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _required_api_key(values: dict[str, object]) -> str:
    value = values.get("api_key")
    if (
        not isinstance(value, str)
        or not value
        or any(character.isspace() for character in value)
        or "\0" in value
    ):
        raise ConfigError("api_key must contain exactly one non-empty key")
    return value


def _required_string(values: dict[str, object], name: str) -> str:
    value = values.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{name} must be a non-empty string")
    return value


def _required_path(values: dict[str, object], name: str) -> Path:
    path = Path(_required_string(values, name))
    if not path.is_absolute():
        raise ConfigError(f"{name} must be an absolute path")
    return path


def _optional_string(values: dict[str, object], name: str) -> str | None:
    value = values.get(name)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{name} must be a non-empty string when set")
    if any(ord(character) < 32 for character in value):
        raise ConfigError(f"{name} must not contain control characters")
    return value


def _optional_integer(values: dict[str, object], name: str) -> int | None:
    value = values.get(name)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{name} must be an integer")
    return value


def _validate_websocket_address(address: str) -> None:
    """Only allow local WebSocket listeners, with a valid TCP port."""
    try:
        parsed = urlsplit(f"//{address}")
        host = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise ConfigError(
            "websocket_address must be a loopback address and port"
        ) from exc
    if (
        host is None
        or port is None
        or parsed.path
        or parsed.query
        or parsed.fragment
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ConfigError("websocket_address must be a loopback address and port")
    try:
        is_loopback = ipaddress.ip_address(host).is_loopback
    except ValueError:
        is_loopback = host.lower() == "localhost"
    if not is_loopback or not 0 <= port <= 65535:
        raise ConfigError(
            "websocket_address must bind to loopback and use a valid port"
        )
