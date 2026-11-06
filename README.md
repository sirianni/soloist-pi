# soloist-pi

A small Python supervisor for running Spotify Soloist on a Raspberry Pi. The
runtime is intended to use only the Python standard library; `uv` manages the
development environment and isolated installation, `pytest` runs the test suite,
and `ruff` handles linting and formatting.

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
just install       # install as an isolated uv tool
just               # list available targets
```

## Build and install

Build distributions with `just build` (or `uv build`).

On the Raspberry Pi, install `uv` and Python 3.13 or newer, copy the wheel to
the Pi, and install it as a uv tool:

```sh
uv tool install ./dist/soloist_pi-0.1.0-py3-none-any.whl
```

`uv tool install` creates and manages a dedicated virtual environment for the
installed command, separate from the system Python environment. The command
will be available on uv's tool bin path (normally `~/.local/bin`). To update
the local installation after building a new wheel, install that wheel with
`uv tool install --force ./dist/soloist_pi-<version>-py3-none-any.whl`.

The project targets Linux arm64 for the Soloist runtime; the Python package
itself is platform-independent. Runtime code will use no third-party Python
dependencies.
