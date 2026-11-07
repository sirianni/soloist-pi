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

## Build and deploy

Run `just check` and `just build` on the development host. The built wheel is
installed on the Pi with Python's built-in `venv` and `pip`; the Pi does not
need `uv`. Production deployment and application upgrades use Ansible. See the
[deployment runbook](deploy/ansible/README.md) for prerequisites, Vault setup,
and commands.

The example supervisor configuration is
[`etc/soloist-pi.toml.example`](etc/soloist-pi.toml.example). Keep the API key
in its separate private file, never in TOML or the systemd unit. The unit
currently runs `--placeholder`, which logs a heartbeat immediately and every
30 seconds. View it with:

```sh
sudo journalctl -u soloist-pi.service -f
```

## Status

Configuration validation, placeholder process supervision, journal-visible
heartbeats, and Ansible deployment have been exercised on a Debian 13 arm64
Pi. The real Soloist binary updater and normal Soloist process launch, plus the
`update` and `ctl` commands, remain pending. See
[`etc/deployment-plan.md`](etc/deployment-plan.md) for the remaining backend
requirements.

The project targets Linux arm64 for the Soloist runtime; the Python package
itself is platform-independent. Runtime code will use no third-party Python
dependencies.

## Related projects
- https://github.com/mintopia/encore
- https://github.com/MopigamesYT/soloistd