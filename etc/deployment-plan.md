# Raspberry Pi deployment and Soloist configuration plan

## Status and scope

This is a deployment/configuration plan, not an Ansible implementation. It
keeps the Python package and runtime standard-library-only while making
configuration and installation repeatable on the Raspberry Pi.

The plan assumes a Debian 13 arm64 Pi. Production installs a built
`soloist-pi` wheel into `/opt/soloist-pi/venv`; systemd runs the installed
`soloist-pi` entry point directly. `uv` is used on the development/control host
for build and package workflows, not on the Pi. Target-side provisioning uses
Python's `venv` module and the environment's `pip`. See
[`installation.md`](installation.md) for the installation direction.

## Configuration model

Spotify's documented Soloist interface is startup command-line options, not a
general-purpose config file. The key and device name are required on every
start. Linux environment variables can override Soloist's data/cache directory
locations, but other documented settings are passed as options. See Spotify's
[command-line reference](https://developer.spotify.com/documentation/soloist/reference/command-line)
and [authentication guide](https://developer.spotify.com/documentation/soloist/concepts/authentication).

`soloist-pi` should provide the managed configuration surface: read a
supervisor-owned TOML file, validate it, read the API key from a separate
private file, and translate the settings to Soloist arguments. Use Python's
standard-library `tomllib`; do not add a runtime dependency. The systemd unit
must not contain configuration values or secrets beyond the config-file path.

Proposed settings:

- `device_name` (required): Spotify Connect name shown in Spotify clients.
- `api_key_file` (required): path to a private file containing the Spotify
  Soloist API key. Do not put the key itself in TOML, command-line arguments to
  `soloist-pi`, the systemd unit, Ansible output, or logs.
- `data_dir` (required): stable Soloist data directory for its Connect session
  and device state. Do not replace or clean it during ordinary deployment.
- `cache_dir` and optional `cache_size_mb`.
- Optional `pipewire_device` and `initial_volume`.
- Optional WebSocket address for local integrations; disabled by default and,
  if enabled, bind to loopback unless a documented use case requires otherwise.

Do not include one-shot pairing or single-track operation flags in the normal
service configuration. Pair the device interactively once using the Spotify
app on the same network; Soloist then persists the Connect session in its data
directory. Ansible must preserve that data across application upgrades and
configuration changes.

The supervisor will still pass the API key to Soloist as a process argument,
because that is Soloist's documented interface. Keep the key out of logs and
service-unit contents, restrict its file to mode `0600`, and document that a
same-user process may be able to inspect process arguments.

## Target layout and ownership

Use separate service-owned locations for configuration, persistent state,
cache, and the managed Soloist executable. Proposed paths (finalize these when
implementing the config loader):

| Purpose | Proposed location | Ownership / mode |
| --- | --- | --- |
| Config and API key | `/var/lib/soloist-pi/config/` | service account, directory `0700`, files `0600` |
| Soloist data/session and supervisor update metadata | `/var/lib/soloist-pi/state/` | service account; private directory |
| Soloist cache | `/var/cache/soloist-pi/` | service account |
| Managed Soloist executable | `/var/lib/soloist-pi/managed/soloist` | service account; writable by supervisor for validated atomic updates |
| Python virtual environment | `/opt/soloist-pi/venv/` | root-owned and not writable by service account |
| systemd unit | `/etc/systemd/system/soloist-pi.service` | root-owned, mode `0644` |

The config file should contain paths and non-secret runtime settings; the API
key file should contain only the key. The Ansible deployment account uses
privilege escalation to install these files with the service account as owner.
Do not place the managed executable inside the Python virtual environment.

## Ansible deployment

If configuration is to be declared and repeatably applied, use Ansible as the
provisioning/deployment interface rather than growing a custom shell installer.
Keep this separate from the Python package, for example under
`deploy/ansible/`. The playbook should:

1. Assert the expected Debian/arm64 target and required Python 3.13 `venv` and
   `ensurepip` provisioning prerequisites.
2. Create the unprivileged `soloist-pi` account and the separated directories
   above with explicit ownership and modes.
3. Create or maintain the root-owned virtual environment with
   `python3.13 -m venv` and install the supplied built wheel using that
   environment's `python -m pip`.
4. Deploy the TOML configuration, API-key file, and unit. Use Ansible Vault
   (or an equivalent secret source) for the API key; do not commit plaintext
   credentials. Secret-handling tasks must suppress task output and diffs.
5. Enable the service on first installation and restart it only when the wheel,
   unit, or effective configuration changes.
6. Never manage or overwrite Soloist's paired session, generated runtime
   metadata, cache contents, or the self-updated Soloist binary as ordinary
   Ansible templates/copies.

Build and deploy flow:

1. Run `just check` and `just build` on the development machine.
2. Run the Ansible playbook against the Pi, passing the exact built wheel as an
   artifact. Do not install from a Git checkout or have systemd invoke `uv`.
3. On first start, select the new Soloist device in the Spotify app on the
   same local network to create the persistent Connect session.
4. For a later `soloist-pi` release, build a new wheel, deploy it, and restart
   the service. This application release is separate from the supervisor's
   validated updates of the Soloist executable.

A later `just deploy PI=...` target may wrap wheel selection and the Ansible
command. Keep the deployment logic in the playbook, not embedded in the
justfile. Do not add Ansible dependencies to the installed Python package.

## Implementation sequence

1. Implement and test the supervisor TOML loader, validation, secret-file
   handling, and argument construction with fake Soloist executables.
2. Settle the final directory paths and add the config path to `soloist-pi run`
   and the systemd unit. Update CLI help and README installation/configuration
   instructions together.
3. Add the Ansible inventory example, playbook, templates, and Vault variable
   conventions in the deployment-only directory. Do not check in a real API
   key or machine-specific secret.
4. Test first install, idempotent re-apply, configuration-triggered restart,
   application upgrade, and preservation of the Connect session and managed
   binary on the target (with no Spotify credentials in automated tests).
5. Document secret rotation, first-time pairing, recovery/re-pairing, and
   application rollback procedures before using this for unattended upgrades.
