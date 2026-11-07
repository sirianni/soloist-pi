# soloist-pi

A small Python supervisor for running Spotify Soloist on a Raspberry Pi. The
runtime is intended to use only the Python standard library; `uv` manages the
development environment and builds packages on the development host, `pytest`
runs the test suite, and `ruff` handles linting and formatting. The Pi uses
Python's built-in `venv` and `pip` to install the wheel; it does not need `uv`.

> The configuration loader and systemd process wrapper are implemented. The
> service currently runs a heartbeat placeholder in place of Spotify Soloist;
> the real Soloist download/update backend is not implemented yet.

## Development

Install [uv](https://docs.astral.sh/uv/), [just](https://just.systems/), and
Python 3.13 or newer. The `justfile` provides the common project targets:

```sh
just sync          # create/update the development environment
just check         # lint, format-check, and pytest
just format        # apply Ruff formatting
just build         # build source and wheel distributions
just clean         # remove generated artifacts
just               # list available targets
```

## Build and install

Build distributions with `just build` (or `uv build`). The production
installation uses the wheel in a dedicated virtual environment at
`/opt/soloist-pi/venv`. Use `uv` on the development host to build the wheel;
the Pi uses Python 3.13's standard-library `venv` module and the environment's
`pip`, not `uv`.

On the Raspberry Pi, install Python 3.13 or newer with its `venv`/`ensurepip`
support, then transfer the built wheel and `etc/soloist-pi.service` to the Pi.
Create a dedicated service
account and the root-owned application directory (run the account creation
once):

```sh
sudo useradd --system --user-group --home-dir /var/lib/soloist-pi --create-home --shell /usr/sbin/nologin soloist-pi
sudo install -d -o root -g root -m 0755 /opt/soloist-pi
```

Create the environment and install the transferred wheel. Replace `VERSION`
with the version in the wheel filename:

```sh
sudo /usr/bin/python3.13 -m venv /opt/soloist-pi/venv
sudo /opt/soloist-pi/venv/bin/python -m pip install --no-deps /tmp/soloist_pi-VERSION-py3-none-any.whl
```

Create the service-owned configuration, state, and cache locations. Keep the
API key in its own file and restrict both files to mode `0600`:

```sh
sudo install -d -o soloist-pi -g soloist-pi -m 0700 /var/lib/soloist-pi/config
sudo install -d -o soloist-pi -g soloist-pi -m 0700 /var/lib/soloist-pi/state/soloist
sudo install -d -o soloist-pi -g soloist-pi -m 0750 /var/cache/soloist-pi
sudo install -o soloist-pi -g soloist-pi -m 0600 etc/soloist-pi.toml.example /var/lib/soloist-pi/config/config.toml
sudoedit /var/lib/soloist-pi/config/config.toml
sudo install -o soloist-pi -g soloist-pi -m 0600 /path/to/your-api-key /var/lib/soloist-pi/config/api-key
```

The TOML file contains `device_name`, absolute `data_dir` and `cache_dir`
paths, and `api_key_file`; the API key itself belongs only in that separate
file. See [`etc/soloist-pi.toml.example`](etc/soloist-pi.toml.example) for
optional cache, PipeWire, volume, and loopback-only WebSocket settings. The
loader rejects group/world-readable configuration or key files and does not
follow symlinks for either file.

Install the unit and start the placeholder service:

```sh
sudo install -o root -g root -m 0644 /tmp/soloist-pi.service /etc/systemd/system/soloist-pi.service
sudo systemctl daemon-reload
sudo systemctl enable --now soloist-pi.service
```

The unit currently passes `--placeholder`: it launches a child process that
writes a heartbeat to stdout immediately and every 30 seconds. systemd sends
stdout and stderr to the journal. Follow the output with:

```sh
sudo journalctl -u soloist-pi.service -f
```

Stop the service with `sudo systemctl stop soloist-pi.service`; the supervisor
forwards `SIGTERM` to the placeholder and waits for it to exit. Remove
`--placeholder` only after the real Soloist backend is implemented. The
supervisor loads and validates the API key now, but the placeholder does not
receive or print it. When the real backend passes the key using Soloist's
command-line interface, a process running as the same user may be able to
inspect that argument.

For an application upgrade, transfer the new wheel, install it into the
existing environment, then restart the service:

```sh
sudo /opt/soloist-pi/venv/bin/python -m pip install --no-deps --upgrade --force-reinstall /tmp/soloist_pi-VERSION-py3-none-any.whl
sudo systemctl restart soloist-pi.service
```

The virtual environment and service unit are root-owned. Run the service as
`soloist-pi`; keep mutable configuration, state, and managed Soloist files in
separate service-owned locations, with the required restrictive permissions.
Do not put the API key in the unit file. See [`etc/installation.md`](etc/installation.md)
for the deployment rationale and [`etc/soloist-pi.service`](etc/soloist-pi.service)
for the unit template.

## Ansible deployment

Repeatable Debian 13 arm64 provisioning is under [`deploy/ansible/`](deploy/ansible/README.md).
It installs the exact built wheel, deploys the private config and Vault-provided
API key, installs the placeholder systemd unit, and preserves runtime state.
No API key or machine-specific inventory is committed.

> **Current status:** configuration validation, `run --placeholder`, signal
> forwarding, journal-visible heartbeat, and the Ansible deployment are
> implemented and have been exercised on `raspberrypi`. The real Soloist binary
> updater and normal Soloist process launch, plus the `update` and `ctl`
> commands, remain pending.

The project targets Linux arm64 for the Soloist runtime; the Python package
itself is platform-independent. Runtime code will use no third-party Python
dependencies.

## Related projects
- https://github.com/mintopia/encore
- https://github.com/MopigamesYT/soloistd