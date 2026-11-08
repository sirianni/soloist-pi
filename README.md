# soloist-pi

A small Python supervisor for running Spotify Soloist on a Raspberry Pi. The
runtime uses HTTPX for CDN requests; `uv` manages the development environment
and builds packages on the development host, `pytest` runs the test suite,
`ruff` handles linting and formatting, and Astral `ty` checks Python types. The
Pi uses Python's built-in `venv` and `pip` to install the wheel; it does not
need `uv`.

> Configuration validation, the safe Soloist updater, and process supervision
> are implemented. The checked-in systemd unit still explicitly selects the
> heartbeat placeholder; remove `--placeholder` to run the real backend.

## Development

Install [uv](https://docs.astral.sh/uv/), [just](https://just.systems/), and
Python 3.13 or newer. The `justfile` provides the common project targets:

```sh
just sync          # create/update the development environment
just check         # lint, format-check, type-check, and pytest
just typecheck     # run Astral ty directly
just lint-ansible  # lint deployment playbook (requires ansible-lint)
just build         # build source and wheel distributions
just deploy        # deploy the built wheel to the configured Pi
# Forward Ansible options, e.g. `just deploy --check --diff`
just format        # apply Ruff formatting
just clean         # remove generated artifacts
just               # list available targets
```

## Build and deploy

Run `just check` and `just build` on the development host. The built wheel is
installed on the Pi with Python's built-in `venv` and `pip`; the Pi does not
need `uv`. Production deployment and application upgrades use Ansible. The Python
package and CLI remain `soloist-pi`; the installed service account/group,
runtime directories, and systemd unit use `soloist`. See the
[deployment runbook](ansible/README.md) for prerequisites, local inventory
setup, and commands. The new names are for clean installs; existing installations
are not migrated automatically.

The example supervisor configuration is
[`etc/soloist.toml.example`](etc/soloist.toml.example). The API key is
stored in the private TOML configuration (mode `0600`), never in the systemd
unit. A process running as the same user may inspect Soloist's arguments. The
checked-in systemd unit currently runs `--placeholder`, which logs a heartbeat
every 30 seconds. The normal `soloist-pi run` path checks the CDN at startup,
falls back to a usable installed binary when the CDN is unavailable, and then
runs Soloist. `soloist-pi update` forces a download and validated installation;
status `10` also forces a refresh before restarting Soloist. The service does
not poll for releases while Soloist is running. View the placeholder journal with:

```sh
sudo journalctl -u soloist.service -f
```

## Status

Configuration validation, placeholder process supervision, journal-visible
heartbeats, and Ansible deployment have been exercised on a Debian 13 arm64
Pi. The updater, startup fallback, expiry retry policy, and Soloist process
handling are covered by offline tests using RESPX mocks, a local HTTP server,
and fake executables. The `ctl` command and production service-unit switch from
`--placeholder` remain pending. See
[`etc/deployment-plan.md`](etc/deployment-plan.md) for remaining work.

The project targets Linux arm64 for the Soloist runtime; the Python package
itself is platform-independent. HTTPX is installed as a runtime dependency in
the production virtual environment.

## Related projects
- https://github.com/mintopia/encore
- https://github.com/MopigamesYT/soloistd