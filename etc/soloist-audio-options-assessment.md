# Soloist audio options assessment

**Basis:** Comparison of `~/Downloads/soloist-pipewire.md`,
`~/Downloads/soloist-pipewire-opt1.md`, and
`etc/headless-audio-stack-plan.md` only. No additional research was done.

## Summary

The dedicated PipeWire stack in `etc/headless-audio-stack-plan.md` best matches
the stated goal: Soloist owns the audio stack and playback does not depend on
`pi`'s login or linger. Its main cost is that it needs custom system services
and still needs a live test.

| Option | Audio server owner / client path | Boot dependency | Main tradeoff |
|---|---|---|---|
| `soloist-pipewire.md` | `pi` owns PipeWire; Soloist connects over the native socket | Requires `pi`'s user services to start, including linger for headless boot; also requires cross-user access to `/run/user/1000` | Native PipeWire path, but exposes Soloist to `pi`'s graph and depends on `pi` |
| `soloist-pipewire-opt1.md` | `pi` owns PipeWire; Soloist connects through an extra PulseAudio socket | Also depends on `pi`'s services and linger | Narrower protocol access, but adds socket permissions/configuration and uses Soloist's PulseAudio path |
| `etc/headless-audio-stack-plan.md` | PipeWire and WirePlumber run as system services under `soloist` | Starts through the system manager; no `pi` login or linger required | Best fit and private by default, but custom units need to be built and tested |

## Assessment

### Shared native socket — `soloist-pipewire.md`

This is the quickest fallback to diagnose: the conversation already established
that a temporary connection from `soloist` to `pi`'s PipeWire worked. It avoids
a second audio daemon and uses the native path, including Soloist's PipeWire
device selection. But it still makes `pi` the audio-server owner, requires
persistent access through `pi`'s private runtime directory, and grants access
to the native graph. That conflicts with the preference for a Soloist-owned
stack independent of `pi`.

The recipe also includes a manual Soloist install/service setup. Do not copy
that wholesale into this project's existing supervisor and packaging.

### Shared Pulse socket — `soloist-pipewire-opt1.md`

This avoids granting access to `/run/user/1000` and limits Soloist to the
PulseAudio interface. But it still depends on `pi`'s server and linger, and
requires a shared runtime directory, a PipeWire Pulse drop-in, and
socket-permission handling.

The document reports a Soloist track-transition bug on the Pulse path and notes
that `--pipewire-device` is ignored there. That bug is asserted in the document
but not supported by a specific citation in its reference list, so treat it as
a reported risk rather than an independently established fact. Either way,
this is the least attractive option for unattended Soloist playback.

### Dedicated system services — `etc/headless-audio-stack-plan.md`

This most directly satisfies the goal. It avoids cross-user socket permissions
and `pi`'s session lifecycle, and retains the native PipeWire path. The cost is
operational: Debian's installed units are user-scoped, so the proposed system
services, runtime directory, environment, and ordering need to be implemented
and tested.

The plan also calls for stopping `pi`'s PipeWire stack to avoid competing for
the same hardware. Other apps would need deliberate access to Soloist's graph
if they should share audio.

## Recommendation

Pursue the dedicated system-service plan as the target. Keep the shared native
socket as a useful diagnostic or fallback if the dedicated services prove
impractical. Do not choose the Pulse-socket option unless testing specifically
shows Soloist behaves reliably on that path.


# External agent evaluation
The assessment puts too much weight on avoiding `pi` as the audio-server owner without establishing that as a requirement. If this Pi’s normal audio stack belongs to `pi`, and Soloist should share it with other applications, **the native-socket option is a pragmatic first choice**: one PipeWire graph, Debian’s packaged user units, and no custom audio daemons.

Linger addresses the main *session-lifecycle* concern: it starts `pi`’s user manager at boot and keeps it running after logout. But it doesn’t guarantee that PipeWire and WirePlumber are enabled and healthy, that the audio device is accessible without a login, or that Soloist recovers after the audio server restarts.

### What remains awkward

- **Cross-user access is a real dependency, not just user-unit awkwardness.** The `soloist` account needs persistent traverse permission on `pi`’s runtime directory *and* permission to connect to the socket. The earlier temporary ACL test showed a connection was possible, but it wasn’t a reboot or recovery test. Use the narrow ACL approach, not membership in the `pi` group plus `0750` on the directory.
- **Startup and recovery need testing.** A socket’s existence doesn’t prove WirePlumber has a usable sink, and ordering after `user-runtime-dir@1000.service` doesn’t order Soloist after the user’s PipeWire units. The current supervisor doesn’t explicitly monitor PipeWire or restart Soloist when the audio server comes back.

I’d also prefer testing `PIPEWIRE_RUNTIME_DIR=/run/user/<pi-uid>` for the native client rather than pointing all of Soloist’s `XDG_RUNTIME_DIR` at another user’s directory. The former is PipeWire-specific; the latter can affect unrelated runtime lookups. Verify this with the actual Soloist build.

### An underweighted fourth option

The dedicated-stack plan itself mentions **packaged user units under the `soloist` account, with linger for `soloist`**. That offers the normal Debian user-service model *and* avoids cross-user socket access and dependence on `pi`. The tradeoff is that it creates a separate graph: `pi`’s audio stack must not compete for the same ALSA device, and `soloist`’s user manager needs its own hardware access. It’s attractive if this is really a dedicated appliance, but less attractive if `pi` also needs normal audio.

### Recommendation

Choose **`soloist-pipewire.md` as the first implementation to validate**, assuming sharing `pi`’s graph and trusting the `soloist` account with it are acceptable. Keep the existing `soloist-pi` supervisor and private configuration; don’t copy the document’s standalone installation, key handling, or expiry behavior.

Before considering it done, test:

1. Cold boot with **no `pi` login**, then playback through the intended physical output.
2. Multiple tracks and the native backend—not just a stream visible in `wpctl`, since Pulse clients also appear in the PipeWire graph.
3. Restart PipeWire/WirePlumber during playback and check whether Soloist reconnects or needs a restart.
4. Reboot and login/logout cycles to verify ACL persistence and hardware access.

If those pass, I wouldn’t introduce custom system-level audio services merely to avoid linger. I haven’t tested these changes on the Pi in this evaluation.

Sources: [systemd linger](https://www.freedesktop.org/software/systemd/man/latest/loginctl.html), [PipeWire socket lookup](https://github.com/pipewire/pipewire/blob/master/doc/dox/internals/protocol.dox), [PipeWire access control](https://github.com/PipeWire/pipewire/blob/master/doc/dox/internals/access.dox).