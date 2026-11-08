# Soloist using `pi`'s native PipeWire socket

**Status:** Proposed implementation plan; not yet deployed or live-tested.

## Decision

Run the existing `soloist-pi` supervisor as the `soloist` system account and
connect its Soloist child process to the native PipeWire socket owned by `pi`.
Keep `pi`'s PipeWire and WirePlumber as the only audio server/session manager;
do not start another audio stack for `soloist`.

This selects the shared-socket approach in `~/Downloads/soloist-pipewire.md`,
not the dedicated system-service approach recommended in the earlier
[`soloist-audio-options-assessment.md`](soloist-audio-options-assessment.md).
The choice accepts dependence on `pi`'s user services and grants Soloist access
to `pi`'s PipeWire graph in exchange for retaining the native PipeWire path
that succeeded in temporary connection testing and avoiding a second audio
stack.

## Goals and boundaries

- Make Soloist connect to `pi`'s PipeWire native socket at headless boot, without
  requiring an interactive `pi` login.
- Keep the existing Python supervisor, managed binary updater, private TOML
  configuration, production virtual environment, and systemd service as the
  way Soloist is installed and launched.
- Preserve the native PipeWire backend so the existing `pipewire_device`
  configuration can select a node when needed.
- Make the native socket reachable by the `soloist` service and verify its
  actual connection to the default sink at service startup.

This plan does **not** install Soloist manually under `/usr/local/bin`, create a
second direct `soloist.service`, put the API key in a systemd environment file
or unit, add a PipeWire Pulse socket, or stop `pi`'s audio services. Per the
user's implementation request, the existing Ansible deployment is the source
of truth for lingering, runtime-directory permissions, and Soloist's PipeWire
readiness configuration.

## Intended runtime layout

- `pi` owns and runs the packaged PipeWire and WirePlumber user services.
  On the inspected Pi, `pi` is UID 1000, PipeWire is 1.4.2, the user units are
  enabled and active, and lingering is currently disabled.
- The active systemd `pipewire.socket` listens on both
  `/run/user/1000/pipewire-0` and `/run/user/1000/pipewire-0-manager`. Both
  sockets currently have mode `0666`; `/run/user/1000` is `0700`, which blocks
  `soloist` from reaching them. The project needs to establish Soloist access,
  not enforce a host-wide socket permission policy.
- `loginctl` lingering for `pi` keeps the user manager and its enabled audio
  services available at boot and after logout; enable it for this design.
- `soloist` remains the account for `/opt/soloist/venv/bin/soloist-pi` and the
  managed Soloist process. The existing TOML file remains the sole source of
  the API key, device name, state path, cache path, and optional PipeWire node.
- Set `PIPEWIRE_RUNTIME_DIR=/run/user/1000` for the Soloist native client and
  leave the supervisor's normal `XDG_RUNTIME_DIR` unchanged. Set
  `PIPEWIRE_REMOTE=pipewire-0` only if testing shows the installed build needs
  it.
- The supervisor service has a bounded readiness gate for both a working native
  PipeWire server and a usable output sink/session-manager graph before Soloist
  starts. Ordering after `user-runtime-dir@<pi-uid>.service` alone is not
  sufficient: it does not order the system service after PipeWire/WirePlumber
  units managed by `pi`'s separate user manager.
- WirePlumber in `pi`'s graph links Soloist's stream to the default output.
  Initially leave `pipewire_device` unset; use the default unless testing shows
  the wrong physical output is selected.

## Implementation plan

### 1. Confirm the target host and baseline

The Pi has been inspected read-only via `ssh pi@raspberrypi` (connection
instructions: [`raspberrypi.md`](raspberrypi.md)). Findings: Debian 13/Trixie,
arm64, `pi` UID/GID 1000, `soloist` UID 999, PipeWire 1.4.2, runtime directory
`/run/user/1000` mode `0700`, and lingering disabled. `pipewire.socket`,
`pipewire.service`, and `wireplumber.service` are enabled and active in the
current `pi` user manager. The default audio sink is `Built-in Audio Stereo`;
no audio sources appeared in the current graph.

The PipeWire socket unit has two stream listeners, `pipewire-0` and
`pipewire-0-manager`; both currently have mode `0666` (the effective
`SocketMode` shown by systemd). A native client test as `soloist` failed while
the parent directory was `0700`, and the `soloist` user cannot traverse that
directory. The socket unit is not managed by this project; validate the required access
through the packaged readiness probe rather than asserting a socket mode.

Keep the existing Soloist service configuration, TOML file, state, and cache
unchanged during this discovery. Do not run a second Soloist process against
the same state directory. Repeat key checks during rollout in case the host
state has changed.

### 2. Make `pi`'s audio session available headlessly

Enable lingering for `pi` (currently `Linger=no`) and ensure the
 distribution-provided PipeWire and WirePlumber user services are enabled and
 started under `pi`. The inspected host has `pipewire.socket`,
`pipewire.service`, and `wireplumber.service` enabled and active in the current
user manager. Confirm after a reboot with no interactive `pi` login that the
user manager, PipeWire socket, WirePlumber, and at least one usable output sink
are present.

Do not treat unit ordering or socket existence as proof of readiness. The
system-level Soloist service and `pi`'s user services are managed by different
systemd managers; explicitly probe the live graph and sink before starting
Soloist.

This is an intentional lifecycle dependency: if `pi`'s user manager or audio
services stop, Soloist loses its audio server. Do not enable a second
PipeWire/WirePlumber stack for `soloist`.

### 3. Make the PipeWire socket reachable by Soloist

On the inspected host, both PipeWire sockets have mode `0666`, while the
runtime directory has mode `0700`, preventing `soloist` from traversing to them.
Persist mode `0711` on the runtime directory whenever logind creates it, using a
system drop-in at
`/etc/systemd/system/user-runtime-dir@1000.service.d/10-pipewire-public.conf`:

```ini
[Service]
ExecStartPost=/usr/bin/chmod 0711 /run/user/1000
```

The project does not set or assert PipeWire socket modes. On this host, the
existing `0666` modes mean other local accounts can also reach the sockets once
the parent directory is traversable; that is a host-level consequence, not a
Soloist requirement. Installing this drop-in does not change an already-existing
runtime directory: mode `0711` takes effect the next time logind creates it.
Do not restart the runtime-directory service just to apply the drop-in; verify
Soloist access after the next runtime-directory creation. The acceptance test
is the packaged readiness probe's actual native connection as `soloist` and
successful query of the default sink.

### 4. Point the existing supervisor at the native socket

Update the existing Ansible-managed system service's durable configuration
so it:

- retains `User=soloist`, its installed `soloist-pi` entry point, existing
  private TOML configuration, and existing supervisor restart/update policy;
- first tests `PIPEWIRE_RUNTIME_DIR=/run/user/<pi-uid>` for the Soloist process,
  leaving `XDG_RUNTIME_DIR` unchanged; tests any need for
  `PIPEWIRE_REMOTE=pipewire-0` against the actual managed Soloist build;
- uses `XDG_RUNTIME_DIR=/run/user/<pi-uid>` only if the native client otherwise
  cannot find the socket, and checks for unintended effects on other runtime
  paths;
- runs the packaged `soloist_pi.pipewire_ready` module as a bounded
  `ExecStartPre` check. It invokes `wpctl get-volume @DEFAULT_AUDIO_SINK@` as
  `soloist`, verifying a live native PipeWire connection and usable default
  sink/session-manager graph rather than only the socket pathname.

Do not claim that `After=user-runtime-dir@<pi-uid>.service` orders the system
service after the PipeWire/WirePlumber user units. Use the readiness gate to
handle startup races across the separate systemd managers. Keep this as
integration with the current supervisor service, not a new unit that invokes
the upstream Soloist binary directly. Keep the API key in the existing
mode-`0600` TOML configuration; never place it in the systemd unit or logs.
Continue to document that same-user processes can inspect Soloist's command-line
arguments.

Leave `pipewire_device` unset initially so WirePlumber's default output is
used. If later testing requires a specific output, use the existing setting
with a stable PipeWire node name, not a transient numeric node ID.

### 5. Validate native playback and boot behavior

1. Restart the existing supervisor service and inspect its journal for startup,
   socket, and audio-backend errors. Do not log the API key or expose it while
   collecting diagnostics.
2. Confirm the Soloist stream appears in `pi`'s PipeWire graph while playback
   is active (for example, with `wpctl status`/`pw-top` as `pi`) and is linked
   to the intended sink.
3. Confirm playback is audible and advances beyond the initial position. If
   Soloist falls back to PulseAudio or the stream is absent from `pi`'s graph,
   treat native PipeWire validation as failed; do not assume successful process
   startup proves the audio path is correct.
4. Initially rely on the default output and keep `pipewire_device` unset.
   Confirm the stream links to the expected physical output and sound is
   audible; investigate the default routing before adding a device pin.
5. Reboot with no interactive `pi` login. Verify lingering, runtime-directory
   traversal, readiness-gate behavior, WirePlumber routing, and playback
   end-to-end.
6. Test recovery after restarting `pi`'s PipeWire and WirePlumber services,
   including socket recreation. Record whether Soloist reconnects on its own.
   The current supervisor does not monitor PipeWire health and a running Soloist
   process is not automatically restarted just because the audio server comes
   back. If it fails to recover, define and test a narrowly scoped restart
   trigger tied to audio-service recovery before considering the integration
   complete; do not add background release polling or change release policy.

### 6. Rollback

Disable the Soloist service before removing its audio environment or socket
access. Remove the audio-specific runtime-directory drop-in, reload the system
manager, and recreate/restart the `pi` runtime directory or reboot to restore
the original permissions. Disable `pi` lingering
only if it was enabled solely for this setup and no other `pi` user services
depend on it. Restore the previous Soloist service configuration and validate
the original audio setup.

Do not remove Soloist's managed binary, TOML configuration, API key, state, or
cache as part of audio rollback. Do not stop `pi`'s PipeWire/WirePlumber during
normal rollout; they are the selected audio server in this design.

## Security and operational tradeoffs

- **Host socket permissions:** The inspected runtime path plus existing `0666`
  socket modes lets other local accounts reach PipeWire, including the manager
  endpoint. This is a consequence of the host's current socket permissions,
  not a socket-mode policy enforced by the project. The project validates the
  required connection as `soloist`.
- **Shared lifecycle:** Soloist depends on `pi`'s user manager, lingering, and
  audio services. A missing socket or stopped server means no audio; this
  design is not independent of `pi`.
- **Permission maintenance:** `/run/user/1000` and its sockets are temporary.
  Logind recreates the directory, so the runtime-directory drop-in reapplies
  mode `0711`. Systemd recreates the sockets with their observed `0666` mode.
- **Shared graph:** Other applications using `pi`'s graph may coexist and be
  mixed by PipeWire, but they share the same graph and routing policy. Apps
  opening ALSA hardware directly may contend with the server.
- **No second audio server:** Starting PipeWire for `soloist` as well would
  risk competing for the same ALSA device and is explicitly out of scope.
- **Backend fallback:** Soloist may initialize a PulseAudio fallback if native
  PipeWire setup fails. The service can appear healthy without the intended
  routing, so graph-level validation is required.

## Resolved choices and remaining checks

The initial output will be WirePlumber's default with `pipewire_device` unset.
The Pi has been inspected read-only: `pi` is UID 1000, both `pipewire.socket`
listeners are currently `0666`, the runtime directory is `0700`, and lingering
is disabled. The implementation is managed by `ansible/site.yaml`: persist the
`0711` runtime-directory mode, enable lingering for `pi`, start its
PipeWire/WirePlumber user services, and configure the Soloist readiness probe.
The playbook does not enforce socket modes.

Do not apply these changes as part of this plan document. At rollout, confirm
the host state again, then live-test Soloist's native socket connection,
readiness against a usable sink, reboot with no interactive `pi` login, and recovery after
PipeWire/WirePlumber restarts.

## Related decision record

See [`soloist-audio-options-assessment.md`](soloist-audio-options-assessment.md)
for the comparison of the shared native socket, shared Pulse socket, and
Soloist-owned system audio stack. This document records the chosen shared native
socket implementation path and its accepted tradeoffs.
