# Ansible deployment

This playbook provisions Debian 13 arm64 and installs a built wheel into the
root-owned `/opt/soloist/venv`. It uses the Pi's built-in Python `venv`
and `pip` to install the wheel; `uv` is not required on the Pi. The playbook
deploys the real `soloist-pi` systemd supervisor. It does not manage the
Soloist session, state, cache contents, or managed binary beyond what the
supervisor manages at runtime. The Python package has no Ansible dependency.

## Prepare inputs

1. Build and test on the development machine:

   ```sh
   just check
   ```

2. Copy `inventory.yaml.example` to `inventory.yaml`, replace the sample host
   with your Pi, and set `api_key` under that host. The real inventory is
   ignored by Git; protect the plaintext key with
   `chmod 600 ansible/inventory.yaml`. The play targets every inventory host,
   so list only hosts intended for this deployment.
3. Ensure Python 3.13 with `venv` and `ensurepip` support is installed on the
   Pi. `uv` is not needed there.
4. Adjust the non-secret defaults in the `vars:` section of `site.yaml`,
   especially the visible device name.

## Validate and deploy

On the development host, optionally lint the playbook with `ansible-lint`
installed:

```sh
just lint-ansible
```

The playbook discovers the wheel at `../dist/soloist_pi-*.whl` relative to
`ansible/site.yaml` and requires exactly one match. `just deploy` builds the
current wheel first, then deploys it:

```sh
just deploy
```

Forward Ansible options as additional recipe arguments. For example, use
check mode and show the proposed changes with:

```sh
just deploy --check --diff
```

If the inventory user needs a sudo password, add `--ask-become-pass` the same
way.

The playbook asserts Debian 13, arm64, Python 3.13+, and `venv`/`ensurepip`
support. Ansible auto-discovers the target Python; the playbook uses that same
interpreter to create the virtual environment. It creates the `soloist`
service account/group and runtime directories, installs the `soloist-pi` wheel,
deploys the private TOML configuration (including the API key) and
`soloist.service`, then enables and starts the service. This naming change is
for clean installs; existing `soloist-pi` installations are not migrated.
Re-applying without changes is idempotent. A changed wheel, key, config, or
unit restarts the service; the persistent Soloist data and cache are not copied
or cleared.

Inspect the service's startup update and Soloist process logs using:

```sh
ansible all -i ansible/inventory.yaml -b \
  -m ansible.builtin.command -a 'journalctl -u soloist.service -n 20 --no-pager'
```

For first-time setup, create/select the Soloist device in Spotify and verify
that the service downloads and launches Soloist successfully. Pairing/session
state is intended to remain in `/var/lib/soloist/state/soloist` across
application upgrades. Rotate the key by updating `api_key` in the local
inventory and re-applying the play; the private TOML configuration is updated
and the service restarted.
