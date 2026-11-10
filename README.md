# soloist-pi

A small Python supervisor for running Spotify Soloist on a Raspberry Pi. The
runtime uses HTTPX for CDN requests; `uv` manages the development environment
and builds packages on the development host, `pytest` runs the test suite,
`ruff` handles linting and formatting, and Astral `ty` checks Python types. The
Pi uses Python's built-in `venv` and `pip` to install the wheel; it does not
need `uv`.

> Configuration validation, the safe Soloist updater, and process supervision
> are implemented. The systemd service runs the real backend through the
> installed `soloist-pi` entry point.

## Development

Install [uv](https://docs.astral.sh/uv/), [just](https://just.systems/), and
Python 3.13 or newer. The `justfile` provides the common project targets:

```sh
just sync          # create/update the development environment
just check         # lint, format-check, type-check, and pytest
just typecheck     # run Astral ty directly
just lint-ansible  # lint deployment playbook (requires ansible-lint)
just build         # build source and wheel distributions
just deploy        # build the wheel, then deploy it to the configured Pi
# Forward Ansible options, e.g. `just deploy --check --diff`
just format        # apply Ruff formatting
just clean         # remove generated artifacts
just               # list available targets
```

## Build and deploy

Run `just check` on the development host. `just deploy` builds the current
wheel before installing it on the Pi. Production deployment and application upgrades use
Ansible.

The Python package is `soloist_pi`; `soloist-pi` runs the supervisor, and
`python -m soloist_pi.update` forces an update. The heartbeat placeholder is
available for development as `python -m soloist_pi.placeholder_supervisor`.
On the Pi, the service runs `/opt/soloist/venv/bin/soloist-pi` directly.
The installed service account/group, runtime directories, and systemd unit use
`soloist`. Ansible configures Soloist to use native PipeWire through `pi`'s
headless user services, configures Soloist's initial stream volume to 100%,
and sets PipeWire's default sink volume to 100% (the `pipewire_sink_volume`
variable in `ansible/site.yaml`). The sink setting affects all audio routed
through that PipeWire sink, not just Soloist. On the inspected host, the
PipeWire sockets are mode `0666`, so making `pi`'s runtime directory traversable
also makes those sockets available to other local accounts; the playbook does
not assert or manage their modes. See the
[deployment runbook](ansible/README.md) for prerequisites, inventory setup, and
commands. The new names are for clean installs; existing
installations are not migrated automatically.

The example supervisor configuration is
[`etc/soloist.toml.example`](etc/soloist.toml.example). The API key is stored
in the private TOML configuration (mode `0600`), never in the systemd unit. A process running as the same user may inspect Soloist's
arguments. The service checks the CDN at startup, falls back to a usable
installed binary when the CDN is unavailable, and then runs Soloist.
`python -m soloist_pi.update` forces a download and validated installation;
status `10` also forces a refresh before restarting Soloist. The service does
not poll for releases while Soloist is running. Follow the service journal
with:

```sh
sudo journalctl -u soloist.service -f
```

## Status

Configuration validation, the updater, startup fallback, expiry retry policy,
and Soloist process handling are covered by offline tests using RESPX mocks, a
local HTTP server, and fake executables. The production service now starts the
real supervisor, and the live CDN download and Soloist launch have been verified
on the Debian 13 arm64 Pi.

The updater selects Spotify's Linux Soloist build for supported `arm64` and
`x86_64` hosts and rejects unsupported platforms before making a request. The
production target remains Linux arm64 Raspberry Pi; the Python package itself
is platform-independent. HTTPX is installed as a runtime dependency in the
production virtual environment.

## Related projects
- https://github.com/mintopia/encore
- https://github.com/MopigamesYT/soloistd