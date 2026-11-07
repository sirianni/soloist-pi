# Agent instructions

## Project identity and scope

- This project is **soloist-pi**: the Python distribution and executable are
  named `soloist-pi`, and the import package is `soloist_pi`.
- It is a Python supervisor for Spotify Soloist on Raspberry Pi / Debian 13
  arm64. Do not rename the project to `soloistd`; existing Soloist config/data
  paths may retain the `soloistd` directory names described in the plan.
- Focus on the Python application and installable packaging. Ansible and
  deployment automation are out of scope unless explicitly requested.
- Keep runtime dependencies to the Python standard library. Use `uv` on the
  development/control host for environment, lockfile, build, and package
  workflows; use Python's `venv` and the environment's `pip` for target-side
  wheel installation. Ruff handles lint/format.

## Layout and development workflow

- Application code belongs in `src/soloist_pi/`; tests belong in `tests/`.
- Use `pytest` for tests. Tests must not require Spotify credentials or access
  to the public network; use local HTTP servers, fixture archives, and fake
  executables when exercising update/process behavior.
- Keep `uv.lock` committed and update it when project dependencies or metadata
  change.
- Use the `justfile` for common tasks: `just sync`, `just check`, `just
  format`, `just build`, and `just clean`.
- Before finishing code changes, run `just check`; run `just build` when
  changing packaging or project metadata.
- Update the README when commands, installation, or user-visible behavior
  changes. Keep CLI help and package entry points in sync.

## Runtime behavior to preserve

Follow the Python implementation plan supplied for this repository:

- Do not poll for updates in the background. Check for an update at service
  startup; do not restart a running Soloist process just because a release is
  published.
- If Soloist exits with status `10`, force-download the current archive and
  restart it, including when the exit happens long after startup. Bound
  immediate repeated expiry retries, while allowing a later refresh after a
  meaningful successful run. Return other exit statuses to the service
  manager.
- On shutdown, forward `SIGTERM` to Soloist, wait for it, and kill it only
  after a timeout.
- When the CDN is unavailable, continue with a usable installed binary; fail
  clearly if no usable binary exists.
- Treat downloads and archives as untrusted: enforce size limits; accept only
  the expected regular `soloist` archive member; reject links and other file
  types; never extract arbitrary paths. Validate a staged executable with
  `soloist --version` and atomically replace the managed binary only after
  validation, preserving the prior working binary on failure.
- Save release metadata atomically and compare available validators (ETag,
  checksum, or Last-Modified). A status-10 refresh must download even if saved
  metadata appears unchanged.
- Keep the API key out of logs and service-unit contents. Protect config
  directories/files with modes `0700`/`0600`; document the same-user process
  argument inspection limitation because Soloist receives the key as an
  argument.

## Packaging and deployment boundaries

- Production installation is from a built wheel into the dedicated
  `/opt/soloist-pi/venv` virtual environment. Create and update that environment
  on the Pi with Python's `venv` module and the environment's `pip`; `uv` is a
  development/control-host tool and must not be required on the Pi. Have systemd
  execute the installed entry point directly; do not depend on a system-wide
  Python package install.
- Keep the Python package platform-independent and standard-library-only; the
  managed Soloist binary is specifically Linux arm64 for the initial target.
- Do not add Ansible roles/playbooks or secret deployment configuration unless
  explicitly asked. Keep any future deployment work separate from the core
  supervisor and package.
