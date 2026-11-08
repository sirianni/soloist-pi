# Headless PipeWire audio stack for Soloist

**Status:** Proposed; the dedicated audio stack has not been implemented. This
is a troubleshooting/design plan, not a record of completed deployment work.

## Recommendation

Run PipeWire and WirePlumber as **system services under the existing `soloist`
account**, and have the Soloist supervisor connect to that private PipeWire
instance. This avoids depending on `pi` logging in or exposing `pi`'s private
audio-session socket. It also avoids enabling linger for `pi`.

Debian's installed PipeWire packages provide user-scoped systemd units, not
system-scoped units. The Pi currently has PipeWire 1.4.2 and WirePlumber 0.5.8;
inspection found their user units but no packaged system units. Therefore this
no-linger design needs small, locally managed system service units. WirePlumber
has a `main-systemwide` profile specifically for running as a system service,
with features that depend on an interactive user session disabled.

An alternative is to use the packaged user units under the `soloist` account
and enable linger for **that service account**. That is the standard Debian
user-service model and needs less custom unit configuration, but still uses
linger. It is not the same as relying on `pi`'s user session. Given the
preference to avoid linger, the system-service design is the proposed route.

## Findings from the Pi

- The real Soloist process runs as the `soloist` system account. Its service
  does not have a PipeWire runtime directory in its environment.
- During playback attempts, Soloist tried PipeWire's fallback socket
  `/run/pipewire/pipewire-0` and then PulseAudio fallback sockets. Those paths
  did not exist. The PipeWire server that was running belonged to `pi` and had
  its socket at `/run/user/1000/pipewire-0`.
- `/run/user/1000` is private to `pi` (mode `0700`). A temporary, execute-only
  ACL test allowed a `soloist` process with `XDG_RUNTIME_DIR=/run/user/1000` to
  connect, confirming that the socket mismatch is real. The test ACL was
  removed; no permission to `pi`'s runtime directory remains.
- PipeWire reported the current default sink as the BCM2835 Headphones analog
  output. The Pi also exposes HDMI audio. Confirm which output is physically
  connected before pinning a sink; do not assume the analog output is correct.
- `/dev/snd` playback devices are owned by the `audio` group. The existing
  Soloist unit has `SupplementaryGroups=audio`, but that setting applies only
  to that unit; each separate PipeWire/WirePlumber system service must also get
  audio-device access.

These observations explain why merely granting the Soloist service the `audio`
group did not fix playback: its audio client could not connect to an audio
server.

## Proposed service layout

Use separate services so systemd can order and restart the audio components:

1. **PipeWire service** (for example, `soloist-pipewire.service`)
   - Run as `User=soloist`, `Group=soloist`, with `SupplementaryGroups=audio`.
   - Have systemd create a private runtime directory such as
     `/run/soloist-audio` with mode `0700`.
   - Set `XDG_RUNTIME_DIR` and `PIPEWIRE_RUNTIME_DIR` to that directory so the
     daemon creates its socket there.
   - Run the packaged `/usr/bin/pipewire`; use an always-started system unit
     rather than relying on an interactive user's socket activation.

2. **WirePlumber service** (for example, `soloist-wireplumber.service`)
   - Run as the same account and with the same runtime directory and audio
     device access.
   - Start after and require the PipeWire service.
   - Run WirePlumber with `--profile=main-systemwide`. This profile is intended
     for system services and disables session-only features such as D-Bus
     device reservation, portal permission storage, and logind seat monitoring.
   - Keep any WirePlumber state in a service-owned state directory, separate
     from Soloist's Spotify session data.

3. **Soloist supervisor service**
   - Continue running the installed supervisor as `soloist` and keep the API
     key in its private config file only.
   - Give it the same `XDG_RUNTIME_DIR`/PipeWire runtime path and order it after
     PipeWire and WirePlumber.
   - Keep the default PipeWire sink initially. If the selected physical output
     is wrong, identify its node name from the dedicated PipeWire graph and use
     the existing `pipewire_device` setting to select it.
   - Add the PipeWire Pulse compatibility service/socket only if testing shows
     Soloist needs the PulseAudio protocol fallback; native PipeWire should be
     tested first.

A system-wide runtime directory with mode `0700` keeps the native PipeWire
socket private to the `soloist` account by default. Other applications can
still share audio if deliberately configured and permitted to connect to this
PipeWire instance. Without that configuration, treat the audio device as
reserved for Soloist. PipeWire itself is designed to mix multiple client
streams before sending them to ALSA; direct ALSA access by another program may
fail while PipeWire owns the device.

## Rollout and validation

1. Confirm the physical output (analog or HDMI) and whether this Pi should be
   dedicated to Soloist audio. The safe initial policy is a private Soloist
   graph, with no other clients.
2. Preserve the current Soloist service config and prepare the two audio units
   without changing the API-key configuration.
3. Stop `pi`'s PipeWire/WirePlumber stack before starting the dedicated server,
   so two PipeWire instances do not contend for the same ALSA device. This will
   stop audio from apps using `pi`'s graph.
4. Start PipeWire and WirePlumber, then verify as `soloist` that the expected
   socket is available and the intended ALSA sink appears in the graph. Check
   the system journal for access errors.
5. Start/restart Soloist and try a track. Confirm a Soloist stream appears in
   the dedicated graph, playback advances beyond `0:00`, and sound reaches the
   connected output.
6. Test a reboot with no `pi` login. The services should start from the system
   manager alone and remain usable.
7. Keep the initial test host-scoped. Only after it works should the durable
   deployment setup be considered for automation; do not add cleanup tasks for
   temporary troubleshooting state.

## Sharing and tradeoffs

With the proposed private socket, the default is effectively exclusive: other
apps will not automatically use Soloist's audio graph. They can share it if
they are intentionally configured as PipeWire clients and granted access; the
PipeWire graph can mix their streams. Apps that try to open the hardware through
ALSA directly may be blocked while PipeWire owns it. Sharing should be an
explicit later choice, not a broad world-writable socket or runtime directory.

The packaged per-user alternative is less custom but requires enabling linger
for the `soloist` account, enabling its PipeWire/WirePlumber user units, adding
`soloist` to the `audio` group, and making the Soloist client run in or point to
that account's runtime directory. The service-unit `SupplementaryGroups=audio`
setting does not grant that group to separate processes launched by the user
manager. This is a valid headless setup if avoiding custom system services
becomes more important than avoiding linger.

## Rollback outline

If the system-scoped stack fails, stop and disable the new PipeWire and
WirePlumber services, remove their service-specific runtime configuration, and
restore the previous Soloist service unit. If audio from the `pi` session is
still wanted, re-enable its PipeWire socket, WirePlumber, and Pulse compatibility
socket. Validate the previous graph before resuming normal playback. Do not
remove or replace Soloist's private config or state as part of audio rollback.

## Primary sources

- Debian's Trixie PipeWire package description (including its packaged user
  service): <https://packages.debian.org/trixie/pipewire>
- PipeWire installation and service startup notes:
  <https://github.com/PipeWire/pipewire/blob/master/INSTALL.md>
- PipeWire daemon and client socket model:
  <https://github.com/PipeWire/pipewire/blob/master/doc/dox/internals/daemon.dox>
- PipeWire socket-directory and environment-variable lookup:
  <https://github.com/PipeWire/pipewire/blob/master/doc/dox/programs/pipewire.1.md>
- PipeWire audio graph and mixing overview:
  <https://docs.pipewire.org/page_overview.html>
- PipeWire native-protocol client access control:
  <https://github.com/PipeWire/pipewire/wiki/Access-control>
- WirePlumber's standard user-service setup:
  <https://pipewire.pages.freedesktop.org/wireplumber/daemon/running.html>
- WirePlumber profiles, including `main-systemwide`:
  <https://pipewire.pages.freedesktop.org/wireplumber/daemon/configuration/components_and_profiles.html>
- WirePlumber D-Bus/session feature behavior for system-wide instances:
  <https://pipewire.pages.freedesktop.org/wireplumber/daemon/configuration/features.html>
- WirePlumber release notes (the system-wide profile was introduced in 0.5.6):
  <https://pipewire.pages.freedesktop.org/wireplumber/resources/releases.html>
- systemd `loginctl enable-linger` behavior, for the per-user alternative:
  <https://www.freedesktop.org/software/systemd/man/latest/loginctl.html>
- systemd service identity, supplementary groups, environment, and runtime
  directories: <https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html>
- systemd service ordering and dependencies:
  <https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html>
- systemd unit dependency semantics:
  <https://www.freedesktop.org/software/systemd/man/latest/systemd.unit.html>
