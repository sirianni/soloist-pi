# Ansible deployment

This playbook provisions Debian 13 arm64 and installs a built wheel into the
root-owned `/opt/soloist-pi/venv`. It uses the Pi's built-in Python `venv`
and `pip` to install the wheel; `uv` is not required on the Pi. The playbook
deploys the placeholder systemd service and does not manage the Soloist
session, state, cache contents, or managed binary. The Python package has no
Ansible dependency.

## Prepare inputs

1. Build and test on the development machine:

   ```sh
   just check
   just build
   ```

2. Copy `inventory.ini.example` to `inventory.ini` and replace the sample host
   with your Pi. The real inventory is ignored by Git.
3. Create the API key secret as an encrypted Vault file:

   ```sh
   ansible-vault create deploy/ansible/group_vars/soloist_pi/vault.yml
   ```

   Define `soloist_pi_api_key` inside it. Do not store a decrypted version in
   the repository. The deployment task suppresses output and diffs for the
   secret.
4. Ensure Python 3.13 with `venv` and `ensurepip` support is installed on the
   Pi. `uv` is not needed there.
5. Adjust the non-secret defaults in
   `group_vars/soloist_pi/main.yml`, especially the visible device name.

## Deploy

Set `WHEEL` to the exact artifact built above, then run:

```sh
WHEEL="$PWD/dist/soloist_pi-VERSION-py3-none-any.whl"
ansible-playbook \
  -i deploy/ansible/inventory.ini \
  deploy/ansible/site.yml \
  -e "wheel_path=$WHEEL" \
  --ask-vault-pass
```

The playbook asserts Debian 13, arm64, Python 3.13+, and `venv`/`ensurepip`
support. It creates the service account and directories, installs the wheel,
deploys the private config/key and unit, then enables and starts the service.
Re-applying without changes is idempotent. A changed wheel, key, config, or
unit restarts the service; the persistent Soloist data and cache are not copied
or cleared.

With the current placeholder unit, inspect the heartbeat using:

```sh
ansible soloist_pi -i deploy/ansible/inventory.ini -b \
  -m ansible.builtin.command -a 'journalctl -u soloist-pi.service -n 20 --no-pager'
```

For first-time setup, create/select the Soloist device in Spotify only after a
real Soloist backend is available. Pairing/session state is intended to remain
in `/var/lib/soloist-pi/state/soloist` across application upgrades. Rotate the
key by changing the Vault value and re-applying the play; the secret file is
replaced privately and the service restarted.
