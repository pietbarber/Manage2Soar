# Ansible Secrets Backup & Restoration

> **"Always remember to always remember, and always remember never to forget."**
>
> The site depends on a set of **gitignored** files that are *not* in git but are
> *required* to (a) keep the Django app running and (b) run every Ansible playbook.
> This runbook and the tooling in it make sure that list never goes stale, is never
> incomplete, and can never be committed by accident.

## What this covers

- **Audit**: verify the required-secret manifest is complete and that every entry is
  gitignored and untracked.
- **Sync**: regenerate `~/bin/ansible-secrets-files.txt` from the single source of truth.
- **Tarball**: build an encrypted-at-rest backup archive of every required secret file.
- **Restore**: how to get a working box / new co-webmaster up and running.

## The single source of truth

| Item | Location | In git? |
|------|----------|---------|
| **Required-secrets manifest** (paths only, no values) | `infrastructure/ansible/required-secrets-manifest.txt` | ✅ **Tracked** (safe — no secrets) |
| `~/bin/ansible-secrets-files.txt` (generated) | `~/bin/ansible-secrets-files.txt` | ❌ Never (outside the repo) |
| The actual secret files themselves | see manifest | ❌ **Never** (gitignored) |

The manifest is the authoritative list. `~/bin/ansible-secrets-files.txt` is a
**generated** copy of it — do not hand-edit it. Regenerate it with `sync`.

## Commands

All commands are run from the project root.

```bash
# 1. Verify the manifest is complete + correct (also runs automatically in pre-commit)
./infrastructure/scripts/audit-ansible-secrets.sh audit

# 2. Print the active file list (no comments)
./infrastructure/scripts/audit-ansible-secrets.sh list

# 3. Regenerate ~/bin/ansible-secrets-files.txt from the manifest
./infrastructure/scripts/audit-ansible-secrets.sh sync

# 4. Build a timestamped backup tarball of every required secret file
./infrastructure/scripts/audit-ansible-secrets.sh tarball
# -> writes ./ansible-secrets-YYYYmmdd-HHMMSS.tar.gz (gitignored)

# 5. Build to a specific location
./infrastructure/scripts/audit-ansible-secrets.sh tarball /secure/location/ansible-secrets.tar.gz
```

### What `audit` checks (exit non-zero on failure)

For **every** entry in the manifest it asserts all three are true:

1. the file **exists** on disk,
2. the file **is gitignored** (`git check-ignore` passes),
3. the file **is not tracked** by git (`git ls-files` does not match).

It also emits a **warning** for any gitignored, secret-looking file that is *not*
in the manifest, so "did you forget to add it?" is surfaced rather than silently
lost.

## Pre-commit enforcement

A `local` pre-commit hook (`audit-ansible-secrets`) runs `audit` on every commit.
This means:

- You **cannot commit** while a required secret file is missing, un-ignored, or
  accidentally tracked.
- If you ever `git rm --cached` or stop ignoring a secret, the commit is blocked
  and the offending path is printed.

## Backup procedure (before changes / regularly)

```bash
./infrastructure/scripts/audit-ansible-secrets.sh audit      # gate: must PASS
./infrastructure/scripts/audit-ansible-secrets.sh sync       # refresh ~/bin list
./infrastructure/scripts/audit-ansible-secrets.sh tarball    # create the archive
```

**Store the tarball securely** (encrypted at rest, off-box / in your vault of choice).

> ⚠️ **The Ansible Vault password is NOT in the tarball.** It is an environment
> value (`ANSIBLE_VAULT_PASSWORD`) or `--vault-id`, not a file. Back it up
> **separately** (password manager / encrypted note) or you cannot decrypt
> `group_vars/all/vault.yml`, `gcp_mail/vault.yml`, etc.

## Restoration (new box / co-webmaster)

Given a working git checkout of the repo at the desired commit:

```bash
# 1. Drop the archive contents back into the project root
tar -xzf ansible-secrets-YYYYmmdd-HHMMSS.tar.gz -C /path/to/project

# 2. Confirm the manifest still matches what you just restored
./infrastructure/scripts/audit-ansible-secrets.sh audit

# 3. Make sure the Vault password is available for the playbooks
export ANSIBLE_VAULT_PASSWORD='<from your secure store>'
#    ...or use: --vault-id @prompt  /  --vault-id myid@/path/to/vault-pass
```

After that, the playbooks run as normal, e.g.:

```bash
cd infrastructure/ansible
ansible-playbook -i inventory/gcp_app.yml playbooks/gcp-app-deploy.yml
```

## Adding / removing a required secret file

1. Add or remove the path in `infrastructure/ansible/required-secrets-manifest.txt`.
2. Make sure the file is listed in `.gitignore` (most are covered by the existing
   `group_vars/gcp_*/vars.yml` & `gcp_*/vault.yml` catch-alls; add a line if not).
3. Run `./infrastructure/scripts/audit-ansible-secrets.sh audit` — it must PASS.
4. Commit the manifest (and `.gitignore` if changed). **The secret file itself must
   stay out of the commit.**
5. Run `sync` and, if you want, `tarball` to refresh the `~/bin` list and backup.

## Conditional / not-required-yet files

Some secrets only exist once a feature is enabled (cluster group_vars, backup
group_vars, a second service-account key). They are present in the manifest as
**commented-out** entries. When you enable the feature, create the file, ensure it
is gitignored, and **uncomment** the line so `audit` starts enforcing it.

### Known naming wrinkle

The repo uses **both** `gcp_backup` *and* `gcs_backup` group names (both appear in
`.gitignore` and as `.example` templates). Standardize on one when you implement
backups so the manifest is unambiguous.
