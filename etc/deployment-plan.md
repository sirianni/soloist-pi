# Remaining Soloist backend work

The configuration loader and Ansible deployment are implemented; see the
[project README](../README.md) and [deployment runbook](../ansible/README.md).
The service still runs the heartbeat placeholder. `soloist-pi run` does not
launch Soloist yet, and the `update` and `ctl` commands are not implemented.

## Backend requirements

Before replacing `--placeholder` with the real backend:

- Check for releases at service startup only. Do not poll in the background or
  restart a running Soloist process because a release appears.
- On Soloist exit status `10`, force-download the current archive and restart,
  even if the exit happens long after startup. Bound immediate expiry retries,
  but allow a later refresh after a meaningful successful run. Return other
  exit statuses to the service manager.
- Launch Soloist with the validated configuration. On shutdown, forward
  `SIGTERM`, wait for the process, and kill it only after a timeout.
- If the CDN is unavailable, continue with a usable installed binary; fail
  clearly if no usable binary exists.
- Treat downloads and archives as untrusted: enforce size limits, accept only
  the expected regular `soloist` member, reject links and other file types,
  and never extract arbitrary paths.
- Validate a staged executable with `soloist --version`, then atomically
  replace the managed binary so failures preserve the previous working copy.
- Save release metadata atomically and compare available validators (ETag,
  checksum, or Last-Modified). A status-10 refresh must download regardless of
  saved metadata.
- Test update and process behavior without Spotify credentials or public
  network access, using local HTTP servers, fixture archives, and fake
  executables.

## Before unattended upgrades

Document recovery and re-pairing if Soloist's session state is lost or
corrupted, and application rollback procedures. The deployment runbook already
covers initial pairing, session preservation across upgrades, and API-key
rotation.
