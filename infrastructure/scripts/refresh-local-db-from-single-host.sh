#!/usr/bin/env bash
# Refresh a local database and profile media from a single-host production snapshot.
#
# Production connection settings are read from the single-host Ansible
# inventory and group variables. Local database defaults come from .env.
#
# Optional environment variables:
#   LOCAL_DB=manage2soar          Local database to replace
#   LOCAL_DB_OWNER=m2s            Owner for the recreated local database
#   LOCAL_MEDIA_ROOT=/path/media   Local Django media root to update
#   SNAPSHOT_DIR=var/prod-snapshots
#
# Options:
#   --yes                Skip the interactive confirmation.
#   --keep-local-backup  Save a pre-refresh dump of the local database.
#   --dry-run            Print the configured operation without making changes.

set -euo pipefail
umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/../.." >/dev/null 2>&1 && pwd)"

ANSIBLE_DIR="${REPO_ROOT}/infrastructure/ansible"
ANSIBLE_INVENTORY="${ANSIBLE_DIR}/inventory/single_host.yml"
ANSIBLE_BIN="${REPO_ROOT}/.venv/bin/ansible"
ANSIBLE_INVENTORY_BIN="${REPO_ROOT}/.venv/bin/ansible-inventory"
PYTHON_BIN="${REPO_ROOT}/.venv/bin/python"
ANSIBLE_VAULT_PASSWORD_FILE="${HOME}/.ansible_vault_pass"
LOCAL_ENV_FILE="${REPO_ROOT}/.env"
SNAPSHOT_DIR="${SNAPSHOT_DIR:-${REPO_ROOT}/var/prod-snapshots}"
ASSUME_YES=false
KEEP_LOCAL_BACKUP=false
DRY_RUN=false
UPDATE_MEDIA=false

usage() {
  printf '%s\n' "Usage: $0 [--yes] [--keep-local-backup] [--dry-run]"
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

for arg in "$@"; do
  case "$arg" in
    --yes) ASSUME_YES=true ;;
    --keep-local-backup) KEEP_LOCAL_BACKUP=true ;;
    --dry-run) DRY_RUN=true ;;
    --help|-h)
      usage
      exit 0
      ;;
    *) die "Unknown option: $arg" ;;
  esac
done

get_env_value() {
  local name="$1"
  local line key value

  [[ -f "$LOCAL_ENV_FILE" ]] || return 1
  while IFS= read -r line || [[ -n "$line" ]]; do
    [[ "$line" == "${name}="* ]] || continue
    key="${line%%=*}"
    value="${line#*=}"
    [[ "$key" == "$name" ]] || continue
    printf '%s\n' "${value%$'\r'}"
    return 0
  done < "$LOCAL_ENV_FILE"
  return 1
}

[[ -x "$ANSIBLE_BIN" ]] || die "Ansible command not found: $ANSIBLE_BIN"
[[ -x "$ANSIBLE_INVENTORY_BIN" ]] || die "Ansible inventory tool not found: $ANSIBLE_INVENTORY_BIN"
[[ -x "$PYTHON_BIN" ]] || die "Project Python environment not found: $PYTHON_BIN"
[[ -f "$ANSIBLE_INVENTORY" ]] || die "Single-host inventory not found: $ANSIBLE_INVENTORY"
[[ -r "$ANSIBLE_VAULT_PASSWORD_FILE" ]] || die "Ansible Vault password file not found: $ANSIBLE_VAULT_PASSWORD_FILE"

ANSIBLE_INVENTORY_ARGS=(--playbook-dir "$ANSIBLE_DIR" -i "$ANSIBLE_INVENTORY" --list --export)
ANSIBLE_INVENTORY_ARGS+=(--vault-password-file "$ANSIBLE_VAULT_PASSWORD_FILE")
ANSIBLE_COMMAND_ARGS=(-i "$ANSIBLE_INVENTORY" single_host --vault-password-file "$ANSIBLE_VAULT_PASSWORD_FILE")

mapfile -t inventory_values < <(
  cd "$ANSIBLE_DIR"
  "$ANSIBLE_INVENTORY_BIN" "${ANSIBLE_INVENTORY_ARGS[@]}" | "$PYTHON_BIN" -c '
import json
import sys

inventory = json.load(sys.stdin)
hosts = inventory.get("single_host", {}).get("hosts", [])
if len(hosts) != 1:
    raise SystemExit("single_host inventory must define exactly one host")

host_name = hosts[0]
hostvars = inventory.get("_meta", {}).get("hostvars", {}).get(host_name, {})
group_vars = inventory.get("single_host", {}).get("vars", {})

def value(name, default=""):
    return str(hostvars.get(name, group_vars.get(name, default)))

print(value("ansible_host", host_name))
print(value("ansible_user"))
print(value("ansible_ssh_private_key_file"))
print(value("ansible_port", "22"))
print(value("postgresql_db", "m2s"))
print(value("m2s_django_media_root", "/var/www/m2s/media"))
'
)

[[ ${#inventory_values[@]} -eq 6 ]] || die "Could not resolve the single-host Ansible inventory."
PROD_SSH_HOST="${inventory_values[0]}"
REMOTE_DB="${inventory_values[4]}"
REMOTE_MEDIA_ROOT="${inventory_values[5]}"

LOCAL_DB_BASE="$(get_env_value DB_NAME || printf '%s' manage2soar)"
LOCAL_DB="${LOCAL_DB:-${LOCAL_DB_BASE}}"
LOCAL_DB_OWNER="${LOCAL_DB_OWNER:-$(get_env_value DB_USER || printf '%s' "$USER")}"
LOCAL_MEDIA_ROOT="${LOCAL_MEDIA_ROOT:-$(get_env_value MEDIA_ROOT || printf '%s' "${REPO_ROOT}/media")}"
[[ "$REMOTE_DB" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || die "REMOTE_DB must be a PostgreSQL identifier."
[[ "$LOCAL_DB" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || die "LOCAL_DB must be a PostgreSQL identifier."
[[ "$LOCAL_DB_OWNER" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || die "LOCAL_DB_OWNER must be a PostgreSQL identifier."
[[ "$REMOTE_MEDIA_ROOT" == /* ]] || die "Ansible m2s_django_media_root must be an absolute path."
[[ "$LOCAL_MEDIA_ROOT" == /* ]] || die "LOCAL_MEDIA_ROOT must be an absolute path."
if "$DRY_RUN"; then
  printf 'Would snapshot production database %s and profile media from Ansible host %s into %s, then replace local database %s and profile media in %s.\n' \
    "$REMOTE_DB" "$PROD_SSH_HOST" "$SNAPSHOT_DIR" "$LOCAL_DB" "$LOCAL_MEDIA_ROOT"
  exit 0
fi

if "$ASSUME_YES"; then
  UPDATE_MEDIA=true
else
  printf 'This will copy production data locally, then permanently replace local database %s. Type the database name to continue: ' \
    "$LOCAL_DB"
  read -r confirmation
  [[ "$confirmation" == "$LOCAL_DB" ]] || die "Confirmation did not match; no production data was copied."

  printf 'Update local profile media in %s too? [y/N]: ' "$LOCAL_MEDIA_ROOT"
  read -r media_confirmation
  case "$media_confirmation" in
    y|Y|yes|YES|Yes) UPDATE_MEDIA=true ;;
    ""|n|N|no|NO|No) ;;
    *) die "Please answer yes or no; no production data was copied." ;;
  esac
fi

for command in pg_restore psql dropdb createdb; do
  command -v "$command" >/dev/null 2>&1 || die "Required command is not installed: $command"
done

if "$KEEP_LOCAL_BACKUP"; then
  command -v pg_dump >/dev/null 2>&1 || die "Required command is not installed: pg_dump"
fi

mkdir -p "$SNAPSHOT_DIR"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
SNAPSHOT_PATH="${SNAPSHOT_DIR}/${REMOTE_DB}-production-${TIMESTAMP}.pgdump"
PARTIAL_SNAPSHOT_PATH="${SNAPSHOT_PATH}.partial"
REMOTE_TEMP_DIR=""
REMOTE_SNAPSHOT_PATH=""
PROFILE_MEDIA_ARCHIVE_PATH="${SNAPSHOT_DIR}/${REMOTE_DB}-profile-media-${TIMESTAMP}.tar.gz"
PARTIAL_PROFILE_MEDIA_ARCHIVE_PATH="${PROFILE_MEDIA_ARCHIVE_PATH}.partial"
REMOTE_PROFILE_MEDIA_ARCHIVE_PATH=""

cleanup() {
  rm -f "$PARTIAL_SNAPSHOT_PATH"
  rm -f "$PARTIAL_PROFILE_MEDIA_ARCHIVE_PATH"
  [[ -z "${MEDIA_STAGING_DIR:-}" ]] || rm -rf "$MEDIA_STAGING_DIR"
  if [[ -n "$REMOTE_TEMP_DIR" ]]; then
    (
    cd "$ANSIBLE_DIR"
    "$ANSIBLE_BIN" "${ANSIBLE_COMMAND_ARGS[@]}" --become \
      -m ansible.builtin.shell \
      -a "rm -rf -- '${REMOTE_TEMP_DIR}'" >/dev/null 2>&1
    ) || true
  fi
}
trap cleanup EXIT

REMOTE_TEMP_DIR="$(
  (
    cd "$ANSIBLE_DIR"
    "$ANSIBLE_BIN" "${ANSIBLE_COMMAND_ARGS[@]}" --become --become-user postgres \
      -m ansible.builtin.tempfile \
      -a "state=directory prefix=manage2soar-refresh-" -o
  ) | "$PYTHON_BIN" -c '
import json
import sys

output = sys.stdin.read().strip()
payload = json.loads(output[output.rfind("{"):])
print(payload["path"])
'
  )"
[[ "$REMOTE_TEMP_DIR" == /* ]] || die "Could not allocate a secure remote temporary directory."
REMOTE_SNAPSHOT_PATH="${REMOTE_TEMP_DIR}/${REMOTE_DB}-local-refresh.pgdump"
REMOTE_PROFILE_MEDIA_ARCHIVE_PATH="${REMOTE_TEMP_DIR}/${REMOTE_DB}-profile-media.tar.gz"

printf 'Creating production snapshot from %s:%s...\n' "$PROD_SSH_HOST" "$REMOTE_DB"
(
  cd "$ANSIBLE_DIR"
  "$ANSIBLE_BIN" "${ANSIBLE_COMMAND_ARGS[@]}" --become --become-user postgres \
    -m ansible.builtin.shell \
    -a "umask 077 && pg_dump -Fc --dbname=${REMOTE_DB} > ${REMOTE_SNAPSHOT_PATH}"
) || die "Production snapshot creation failed."
(
  cd "$ANSIBLE_DIR"
  "$ANSIBLE_BIN" "${ANSIBLE_COMMAND_ARGS[@]}" --become \
    -m ansible.builtin.command \
    -a "chmod 600 '${REMOTE_SNAPSHOT_PATH}'"
) || die "Production snapshot permission hardening failed."

(
  cd "$ANSIBLE_DIR"
  "$ANSIBLE_BIN" "${ANSIBLE_COMMAND_ARGS[@]}" --become \
    -m ansible.builtin.fetch \
    -a "src=${REMOTE_SNAPSHOT_PATH} dest=${PARTIAL_SNAPSHOT_PATH} flat=true validate_checksum=true"
) || die "Production snapshot download failed."
[[ -s "$PARTIAL_SNAPSHOT_PATH" ]] || die "Production snapshot is empty."
mv "$PARTIAL_SNAPSHOT_PATH" "$SNAPSHOT_PATH"

printf 'Validating snapshot %s...\n' "$SNAPSHOT_PATH"
pg_restore --list "$SNAPSHOT_PATH" >/dev/null \
  || die "Downloaded snapshot is not a valid PostgreSQL custom-format dump."

if "$UPDATE_MEDIA"; then
  printf 'Creating profile-media archive from %s...\n' "$REMOTE_MEDIA_ROOT"
  remote_media_archive_args="$("$PYTHON_BIN" -c '
import json
import sys

print(json.dumps({"argv": [
    "tar", "-C", sys.argv[1], "-czf", sys.argv[2],
    "profile_photos", "generated_avatars",
]}))
' "$REMOTE_MEDIA_ROOT" "$REMOTE_PROFILE_MEDIA_ARCHIVE_PATH")"
  (
    cd "$ANSIBLE_DIR"
    "$ANSIBLE_BIN" "${ANSIBLE_COMMAND_ARGS[@]}" --become \
      -m ansible.builtin.command \
      -a "$remote_media_archive_args"
  ) || die "Production profile-media archive creation failed."
  (
    cd "$ANSIBLE_DIR"
    "$ANSIBLE_BIN" "${ANSIBLE_COMMAND_ARGS[@]}" --become \
      -m ansible.builtin.command \
      -a "chmod 600 '${REMOTE_PROFILE_MEDIA_ARCHIVE_PATH}'"
  ) || die "Production profile-media archive permission hardening failed."
  (
    cd "$ANSIBLE_DIR"
    "$ANSIBLE_BIN" "${ANSIBLE_COMMAND_ARGS[@]}" --become \
      -m ansible.builtin.fetch \
      -a "src=${REMOTE_PROFILE_MEDIA_ARCHIVE_PATH} dest=${PARTIAL_PROFILE_MEDIA_ARCHIVE_PATH} flat=true validate_checksum=true"
  ) || die "Production profile-media archive download failed."
  tar -tzf "$PARTIAL_PROFILE_MEDIA_ARCHIVE_PATH" >/dev/null \
    || die "Downloaded profile-media archive is invalid."
  mv "$PARTIAL_PROFILE_MEDIA_ARCHIVE_PATH" "$PROFILE_MEDIA_ARCHIVE_PATH"
fi

if "$KEEP_LOCAL_BACKUP"; then
  LOCAL_BACKUP_PATH="${SNAPSHOT_DIR}/${LOCAL_DB}-before-refresh-${TIMESTAMP}.pgdump"
  if psql --username="$LOCAL_DB_OWNER" --dbname=postgres --tuples-only --no-align \
    --command="SELECT 1 FROM pg_database WHERE datname = '${LOCAL_DB}'" | grep -qx 1; then
    printf 'Saving current local database to %s...\n' "$LOCAL_BACKUP_PATH"
    pg_dump --username="$LOCAL_DB_OWNER" --format=custom --file="$LOCAL_BACKUP_PATH" "$LOCAL_DB"
  else
    printf 'Local database %s does not exist; no local backup created.\n' "$LOCAL_DB"
  fi
fi

printf 'Replacing local database %s...\n' "$LOCAL_DB"
psql --username="$LOCAL_DB_OWNER" --dbname=postgres --quiet \
  --command="SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '${LOCAL_DB}' AND pid <> pg_backend_pid();"
dropdb --username="$LOCAL_DB_OWNER" --if-exists "$LOCAL_DB"
createdb --username="$LOCAL_DB_OWNER" --owner="$LOCAL_DB_OWNER" "$LOCAL_DB"
pg_restore --username="$LOCAL_DB_OWNER" --dbname="$LOCAL_DB" --no-owner --no-privileges --exit-on-error "$SNAPSHOT_PATH"
psql --username="$LOCAL_DB_OWNER" --dbname="$LOCAL_DB" --quiet --command='SELECT 1;' >/dev/null

if "$UPDATE_MEDIA"; then
  printf 'Replacing local profile media in %s...\n' "$LOCAL_MEDIA_ROOT"
  mkdir -p "$LOCAL_MEDIA_ROOT"
  MEDIA_STAGING_DIR="$(mktemp -d "${LOCAL_MEDIA_ROOT}/.refresh-profile-media.XXXXXX")"
  tar -xzf "$PROFILE_MEDIA_ARCHIVE_PATH" -C "$MEDIA_STAGING_DIR"
  mkdir -p "${MEDIA_STAGING_DIR}/profile_photos" "${MEDIA_STAGING_DIR}/generated_avatars"
  rm -rf "${LOCAL_MEDIA_ROOT}/profile_photos" "${LOCAL_MEDIA_ROOT}/generated_avatars"
  mv "${MEDIA_STAGING_DIR}/profile_photos" "${MEDIA_STAGING_DIR}/generated_avatars" "$LOCAL_MEDIA_ROOT/"
  rm -rf "$MEDIA_STAGING_DIR"
  MEDIA_STAGING_DIR=""
fi

if "$UPDATE_MEDIA"; then
  printf 'Local database %s and profile media refreshed successfully. Snapshots retained at %s and %s\n' \
    "$LOCAL_DB" "$SNAPSHOT_PATH" "$PROFILE_MEDIA_ARCHIVE_PATH"
else
  printf 'Local database %s refreshed successfully. Snapshot retained at %s\n' "$LOCAL_DB" "$SNAPSHOT_PATH"
fi
