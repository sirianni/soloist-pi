# System-service installation direction

## Decision

Install `soloist-pi` from a built wheel into a dedicated virtual environment at
`/opt/soloist-pi/venv`. Do not use a Git checkout as the production installation
and do not have the systemd unit invoke `uv`.

Use `uv` during provisioning or an explicit upgrade to create/manage the
environment and install the wheel. At runtime, systemd should execute the
installed entry point directly:

```ini
ExecStart=/opt/soloist-pi/venv/bin/soloist-pi run
```

The package and virtual environment should be root-owned and not writable by
the service account. Run the service as a dedicated unprivileged user. Keep
mutable configuration, state, and the managed Soloist binary in separate
service-owned locations with the required restrictive permissions; the
supervisor needs write access to the managed binary location to perform its
validated updates.

## Operational notes

- Build and transfer a wheel to the Raspberry Pi; install that artifact into
  the dedicated environment.
- Updating `soloist-pi` is an administrative deployment step followed by a
  service restart. It is separate from the supervisor's updates of the Soloist
  binary.
- The service must not depend on an interactive shell, a user's `PATH`, or a
  `uv` executable being available at runtime.
- Provisioning and upgrade commands are documented in the README; the
  accompanying `etc/soloist-pi.service` is the systemd unit template. The unit
  cannot run successfully until the supervisor's `run` command is implemented.
