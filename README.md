# soloist-pi

A small Python supervisor for running Spotify Soloist on a Raspberry Pi. The
runtime is intended to use only the Python standard library; `uv` manages the
development environment and provisions the production virtual environment,
`pytest` runs the test suite, and `ruff` handles linting and formatting.

> The supervisor behavior is not implemented yet. This repository currently
> contains project and packaging scaffolding only.

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
`/opt/soloist-pi/venv`. `uv` is only needed when provisioning or upgrading the
installation; systemd executes the installed command directly.

On the Raspberry Pi, install Python 3.13 or newer and `uv`, then transfer the
built wheel and `etc/soloist-pi.service` to the Pi. Create a dedicated service
account and the root-owned application directory (run the account creation
once):

```sh
sudo useradd --system --user-group --home-dir /var/lib/soloist-pi --create-home --shell /usr/sbin/nologin soloist-pi
sudo install -d -o root -g root -m 0755 /opt/soloist-pi
```

Create the environment and install the transferred wheel. Replace `VERSION`
with the version in the wheel filename:

```sh
UV="$(command -v uv)"
sudo "$UV" venv --python 3.13 /opt/soloist-pi/venv
sudo "$UV" pip install --python /opt/soloist-pi/venv/bin/python /tmp/soloist_pi-VERSION-py3-none-any.whl
```

Install the unit. Once the `run` command is implemented, enable and start the
service:

```sh
sudo install -o root -g root -m 0644 /tmp/soloist-pi.service /etc/systemd/system/soloist-pi.service
sudo systemctl daemon-reload
sudo systemctl enable --now soloist-pi.service
```

For an application upgrade, transfer the new wheel, install it into the
existing environment, then restart the service:

```sh
UV="$(command -v uv)"
sudo "$UV" pip install --python /opt/soloist-pi/venv/bin/python /tmp/soloist_pi-VERSION-py3-none-any.whl
sudo systemctl restart soloist-pi.service
```

The virtual environment and service unit are root-owned. Run the service as
`soloist-pi`; keep mutable configuration, state, and managed Soloist files in
separate service-owned locations, with the required restrictive permissions.
Do not put the API key in the unit file. See [`etc/installation.md`](etc/installation.md)
for the deployment rationale and [`etc/soloist-pi.service`](etc/soloist-pi.service)
for the unit template.

> **Current status:** the CLI and supervisor behavior are still scaffolding.
> The wheel can be built and installed, but the `run` command is not yet
> implemented, so the service is not operational until that work is completed.

The project targets Linux arm64 for the Soloist runtime; the Python package
itself is platform-independent. Runtime code will use no third-party Python
dependencies.
