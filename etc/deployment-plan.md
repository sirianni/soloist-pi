# Soloist integration status

The configuration loader, safe updater, and real `soloist-pi` backend are
implemented. The systemd/Ansible service now starts the installed `soloist-pi`
entry point. The first live CDN download and Soloist launch on the Debian 13
arm64 Pi still need to be verified. See the [project README](../README.md) and
[deployment runbook](../ansible/README.md).

The backend enforces the following behavior, covered by offline tests using
local HTTP servers, fixture archives, and fake executables:

- Check for releases at service startup only. Do not poll in the background or
  restart a running Soloist process because a release appears.
- On Soloist exit status `10`, force-download the current archive and restart,
  even if the exit happens long after startup. Bound immediate expiry retries,
  but allow a later refresh after a meaningful successful run. Stop cleanly after
  retry exhaustion or a failed forced refresh to avoid a systemd restart loop;
  return other exit statuses to the service manager.
- Launch Soloist with the validated configuration. On shutdown, forward
  `SIGTERM`, wait for the process, and kill it only after a timeout.
- If the CDN is unavailable, continue with a usable installed binary; fail
  clearly if no usable binary exists.
- Treat downloads and archives as untrusted: enforce size limits; require one
  exact, regular `soloist` member; ignore other regular files and directories
  without extracting them; reject links and special file types; and never
  extract arbitrary paths.
- Validate a staged executable with `soloist --version`, then atomically
  replace the managed binary and release metadata while preserving the previous
  working copy if validation or commit fails.
- Compare available release validators (ETag, CRC32C header, or Last-Modified
  plus Content-Length). A status-10 refresh and explicit
  `python -m soloist_pi.update` command always download regardless of saved
  metadata.

## Remaining work

- Define and implement the `ctl` command if control operations are needed.
- Deploy the updated service unit to the Debian 13 arm64 Pi and verify the live
  CDN download, staged `soloist --version` validation, and Soloist startup.
- Before unattended upgrades, document recovery and re-pairing if Soloist's
  session state is lost or corrupted, plus application rollback procedures.
  The deployment runbook already covers initial pairing, session preservation
  across upgrades, and API-key rotation.
