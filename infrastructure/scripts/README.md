# Infrastructure Scripts

## Refresh a local test database

`refresh-local-db-from-single-host.sh` captures a fresh custom-format backup
from a single-host production PostgreSQL instance, keeps it locally, and
replaces the local database only after the backup has been validated. Before
starting, it asks whether to also copy `profile_photos/` and
`generated_avatars/` from the production media root. `--yes` refreshes both
the database and profile media without prompting.

Production data can contain member and financial information. Snapshots are
stored with mode `0600` under the ignored `var/prod-snapshots/` directory; do
not copy them to an unencrypted or shared location.

The script reads the production host, SSH user, private key, port, and
`postgresql_db` directly from
`infrastructure/ansible/inventory/single_host.yml` and its Ansible group
variables. The production SSH account must be able to run
`sudo -u postgres pg_dump`. The script runs its remote operations through
Ansible, which automatically loads `ansible_become_password` from
`group_vars/single_host/vault.yml` with `~/.ansible_vault_pass`; the sudo
password is never exposed to the script or command line.

It reads `DB_NAME` and `DB_USER` from `.env` and targets `DB_NAME` as the
local database. It reads `MEDIA_ROOT` from `.env` for the local profile-media
destination. Local PostgreSQL credentials are resolved normally, such as
through `.pgpass`.

```bash
infrastructure/scripts/refresh-local-db-from-single-host.sh
```

The Ansible PostgreSQL role defaults production database name to `m2s` when it
is not set in group variables. Override the local destination only when needed:

```bash
LOCAL_DB=other_test_db LOCAL_DB_OWNER="$USER" \
  infrastructure/scripts/refresh-local-db-from-single-host.sh --keep-local-backup
```

The script requires the exact target database name before copying production
data and, for interactive runs, separately asks whether to refresh profile
media. Use `--yes` only in trusted automation. Use `--dry-run` to confirm the
resolved settings without connecting to either server.
