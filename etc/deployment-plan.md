# Raspberry Pi deployment and Soloist configuration

## Current status

The supervisor TOML loader with an embedded API key, placeholder process
supervision, systemd unit, and Ansible wheel deployment are implemented. The
Ansible deployment has been exercised on Debian 13 arm64 with the placeholder
service and re-applied idempotently. See the [deployment runbook](../ansible/README.md)
and the [project README](../README.md).

The Pi uses Python 3.13's built-in `venv` and the environment's `pip` to install
the `soloist-pi` wheel into `/opt/soloist/venv`. `uv` is used on the
development/control host for build and package workflows; it is not a Pi
prerequisite. systemd executes the installed `soloist-pi` entry point directly
from the `soloist.service` unit under the `soloist` account/group.

The current unit explicitly runs `--placeholder`, which writes a heartbeat to
stdout every 30 seconds. Add the API key to the ignored local inventory before
deploying a real Soloist backend. The placeholder does not use the key.

## Configuration and paths

Spotify Soloist is configured through startup options, not a general-purpose
config file. `soloist-pi` provides a service-owned TOML layer, validates it,
reads the API key from the private TOML config, and builds Soloist arguments.
Use Python's standard-library `tomllib`; do not add a runtime dependency.

Required TOML settings:

- `device_name`: Spotify Connect name.
- `api_key`: Spotify Soloist API key; the TOML file must remain mode `0600`.
- `data_dir`: persistent Soloist device/session state.
- `cache_dir`: volatile playback cache.

Optional settings are `cache_size_mb`, `pipewire_device`, `initial_volume`, and
`websocket_address`. WebSocket listeners are loopback-only. Do not put one-shot
pairing or single-track flags in normal service configuration. See
[`soloist.toml.example`](soloist.toml.example).

| Purpose | Path | Ownership / mode |
| --- | --- | --- |
| Config including API key | `/var/lib/soloist/config/config.toml` | service account, directory `0700`, file `0600` |
| Persistent state and update metadata | `/var/lib/soloist/state/` | service account, private |
| Soloist data/session | `/var/lib/soloist/state/soloist/` | service account, private; preserve across upgrades |
| Soloist cache | `/var/cache/soloist/` | service account |
| Managed Soloist executable | `/var/lib/soloist/bin/soloist` | service account; validated atomic updates only |
| Python virtual environment | `/opt/soloist/venv/` | root-owned; not writable by service account |
| systemd unit | `/etc/systemd/system/soloist.service` | root-owned, mode `0644` |

The service unit contains no secret or runtime settings beyond the config-file
path and the current placeholder-mode switch. The real Soloist interface
requires its API key as an argument; keep it out of logs and document that a
process running as the same user may inspect process arguments.

## Deployment boundary

Ansible lives under `ansible/`, separate from the Python package. It
asserts Debian 13 arm64, Python 3.13, `venv`, and `ensurepip`; creates the
service account and separated directories; installs the exact built wheel into
the root-owned virtual environment; deploys TOML containing the host-provided
API key and the unit; and enables the service. Re-application should be
idempotent. It must not copy or overwrite paired session data, generated
runtime metadata, cache contents, or the self-updated Soloist executable.

Build with `just check` and `just build` on the development host. Deploy the
wheel artifact, not a Git checkout. See the
[Ansible runbook](../ansible/README.md) for inventory and command details. The
installed package remains standard-library-only and has no Ansible dependency.

## Remaining Soloist backend work

The placeholder is an integration smoke test, not a Soloist substitute for
production. Before removing `--placeholder`, implement and test:

- startup release checks only; do not poll in the background or restart a
  running Soloist process because a release appears;
- on exit status `10`, force-download the current archive and restart even if
  the exit occurs long after startup; bound immediate expiry retries while
  allowing later refresh after a meaningful successful run;
- forward `SIGTERM`, wait for the process, and kill only after a timeout;
- continue with a usable installed binary when the CDN is unavailable, and
  fail clearly if no usable binary exists;
- enforce download/archive size limits; accept only the expected regular
  `soloist` member, reject links and other file types, and never extract
  arbitrary paths;
- validate a staged executable with `soloist --version`, then atomically
  replace the managed binary so failures preserve the previous working copy;
- save release metadata atomically and compare available ETag, checksum, or
  Last-Modified validators; status-10 refreshes must download regardless of
  saved metadata;
- keep API keys out of logs and systemd unit contents.

Before unattended upgrades, document real-device pairing, session preservation
and recovery/re-pairing, key rotation, and application rollback. Automated tests
must not need Spotify credentials or public network access.
