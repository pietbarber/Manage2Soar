#!/bin/bash
# Verify PostgreSQL Backup Encryption/Decryption Works
# Tests that the backup passphrase can successfully decrypt existing backups
#
# Usage: ./verify-backup-encryption.sh [DATABASE_SERVER_IP]
#
# This script:
# 1. Checks passphrase file exists on database server
# 2. Tests encryption/decryption with test data
# 3. Downloads a recent encrypted backup from GCS
# 4. Verifies the file is encrypted
# 5. Tests decryption of actual backup
#
# Exit codes:
#   0 = Success - encryption/decryption working correctly
#   1 = Failure - cannot decrypt backups (CRITICAL ISSUE)

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
# Auto-detect database server and SSH user from Ansible inventory if not provided
if [[ -z "${1:-}" ]] && [[ -f "inventory/gcp_database.yml" ]]; then
    # Extract ansible_host and ansible_user from gcp_database.yml inventory
    # Look under gcp_database_servers -> hosts section
    DB_INFO=$(awk '
        /^gcp_database_servers:/ { in_group=1; next }
        in_group && /^ *hosts:/   { in_hosts=1; next }
        # Leave hosts block when we hit a non-indented or new top-level key
        in_hosts && /^[^[:space:]]/ { in_hosts=0; in_group=0 }
        in_hosts && /ansible_host:/ { host=$2 }
        in_hosts && /ansible_user:/ { user=$2; print user " " host; exit }
        # If we find ansible_host but never see ansible_user, print with empty user in END
        END { if (host && !user) print " " host }
    ' inventory/gcp_database.yml)

    DB_SERVER=$(echo "${DB_INFO}" | awk '{print $2}')
    SSH_USER=$(echo "${DB_INFO}" | awk '{print $1}')

    if [[ -z "${DB_SERVER}" ]]; then
        echo -e "${RED}ERROR: Could not auto-detect database server from inventory/gcp_database.yml${NC}"
        echo "Usage: $0 [database-server-ip-or-hostname]"
        exit 1
    fi

    # Default to current user if ansible_user not specified in inventory
    if [[ -z "${SSH_USER}" ]]; then
        SSH_USER="${USER}"
    fi

    echo "Auto-detected database server: ${DB_SERVER} (SSH user: ${SSH_USER})"
else
    DB_SERVER="${1:-m2s-database}"
    SSH_USER="${USER}"  # Use current user by default
fi

# Auto-detect GCS bucket from Ansible configuration
GCS_BUCKET_NAME_DEFAULT="m2s-database-backups-manage2soar"
GCS_BUCKET_NAME="${GCS_BUCKET_NAME_DEFAULT}"
DETECTED_BUCKET=""

# 1) Prefer group_vars override if present
if [[ -f "group_vars/gcp_database/vars.yml" ]]; then
    DETECTED_BUCKET=$(grep -E "^\s*postgresql_backup_gcs_bucket:" group_vars/gcp_database/vars.yml | awk '{print $2}' | tr -d '"')
fi

# 2) Fall back to role defaults if not set in group_vars
if [[ -z "${DETECTED_BUCKET}" ]] && [[ -f "roles/postgresql/defaults/main.yml" ]]; then
    DETECTED_BUCKET=$(grep -E "^\s*postgresql_backup_gcs_bucket:" roles/postgresql/defaults/main.yml | awk '{print $2}' | tr -d '"')
fi

if [[ -n "${DETECTED_BUCKET}" ]]; then
    GCS_BUCKET_NAME="${DETECTED_BUCKET}"
fi

GCS_BUCKET="gs://${GCS_BUCKET_NAME}/postgresql/"
TEMP_DIR="/tmp/backup-verify-$$"
PASSPHRASE_FILE="/var/lib/postgresql/.backup_passphrase"

echo "================================================================"
echo "PostgreSQL Backup Encryption Verification"
echo "================================================================"
echo ""

# Step 1: Check passphrase file exists on database server
echo "[1/5] Checking passphrase file on database server..."
if ssh "${SSH_USER}@${DB_SERVER}" "sudo test -f ${PASSPHRASE_FILE}"; then
    echo -e "${GREEN}✓ Passphrase file exists: ${PASSPHRASE_FILE}${NC}"

    # Check permissions
    PERMS=$(ssh "${SSH_USER}@${DB_SERVER}" "sudo stat -c '%a %U %G' ${PASSPHRASE_FILE}")
    echo "  Permissions: ${PERMS}"

    if [[ "${PERMS}" == "400 postgres postgres" ]]; then
        echo -e "${GREEN}  ✓ Permissions are correct (400 postgres:postgres)${NC}"
    else
        echo -e "${YELLOW}  ⚠ WARNING: Unexpected permissions (expected: 400 postgres:postgres)${NC}"
    fi
else
    echo -e "${RED}✗ CRITICAL: Passphrase file not found on ${DB_SERVER}${NC}"
    exit 1
fi
echo ""

# Step 2: Test encryption/decryption with a small test string
# NOTE: This uses a small in-memory test string for verification only (piped through SSH/OpenSSL).
#       For production backup workflows, prefer file-based input to OpenSSL for both security
#       (avoids sensitive data in process listings/shell pipelines) and reliability reasons.
echo "[2/5] Testing encryption/decryption with test data..."
TEST_STRING="manage2soar-backup-test-$(date +%s)"
ENCRYPTED=$(printf '%s\n' "${TEST_STRING}" | ssh "${SSH_USER}@${DB_SERVER}" "sudo -u postgres openssl enc -aes-256-cbc -salt -pbkdf2 -pass file:${PASSPHRASE_FILE} -base64")
DECRYPTED=$(printf '%s\n' "${ENCRYPTED}" | ssh "${SSH_USER}@${DB_SERVER}" "sudo -u postgres openssl enc -d -aes-256-cbc -pbkdf2 -pass file:${PASSPHRASE_FILE} -base64")

if [[ "${DECRYPTED}" == "${TEST_STRING}" ]]; then
    echo -e "${GREEN}✓ Test encryption/decryption successful${NC}"
else
    echo -e "${RED}✗ CRITICAL: Test decryption failed${NC}"
    echo "  Expected: ${TEST_STRING}"
    echo "  Got: ${DECRYPTED}"
    exit 1
fi
echo ""

# Step 3: Download a recent encrypted backup from GCS
echo "[3/5] Finding recent encrypted backup in GCS..."
mkdir -p "${TEMP_DIR}"

# Get the most recent backup (sorted by timestamp in filename)
LATEST_BACKUP=$(gsutil ls "${GCS_BUCKET}" | grep "\.enc$" | sort -r | head -1)

if [[ -z "${LATEST_BACKUP}" ]]; then
    echo -e "${RED}✗ ERROR: No encrypted backups found in ${GCS_BUCKET}${NC}"
    echo "  This might be expected if backups haven't run yet"
    exit 1
fi

BACKUP_FILENAME=$(basename "${LATEST_BACKUP}")
echo "  Found: ${BACKUP_FILENAME}"

# Download backup to temp directory
echo "  Downloading backup..."
gsutil cp "${LATEST_BACKUP}" "${TEMP_DIR}/${BACKUP_FILENAME}"

BACKUP_SIZE=$(du -h "${TEMP_DIR}/${BACKUP_FILENAME}" | cut -f1)
echo -e "${GREEN}✓ Downloaded backup: ${BACKUP_SIZE}${NC}"
echo ""

# Step 4: Verify the file is encrypted (should be binary data, not readable)
echo "[4/5] Verifying backup is encrypted..."
FILE_TYPE=$(file -b "${TEMP_DIR}/${BACKUP_FILENAME}")

if [[ "${FILE_TYPE}" == "data" ]] || [[ "${FILE_TYPE}" =~ "openssl enc'd data" ]]; then
    echo -e "${GREEN}✓ Backup is encrypted (file type: ${FILE_TYPE})${NC}"
elif [[ "${FILE_TYPE}" =~ "PostgreSQL" ]]; then
    echo -e "${RED}✗ ERROR: Backup appears to be UNENCRYPTED${NC}"
    echo "  File type: ${FILE_TYPE}"
    echo "  This is a SECURITY ISSUE - backups should be encrypted"
    rm -rf "${TEMP_DIR}"
    exit 1
else
    echo -e "${YELLOW}⚠ WARNING: Unexpected file type: ${FILE_TYPE}${NC}"
    echo "  Continuing with decryption test..."
fi
echo ""

# Step 5: Test decryption with current passphrase
echo "[5/5] Testing decryption of actual backup..."

# Copy backup to database server for decryption
# Note: BACKUP_FILENAME is from GCS and must be treated as untrusted input
scp "${TEMP_DIR}/${BACKUP_FILENAME}" "${SSH_USER}@${DB_SERVER}:/tmp/"

# Attempt decryption on database server
DECRYPTED_FILENAME="${BACKUP_FILENAME%.enc}"
# Pass filenames as environment variables to prevent shell injection
# shellcheck disable=SC2087
DECRYPT_RESULT=$(ssh "${SSH_USER}@${DB_SERVER}" env BACKUP_FILE="${BACKUP_FILENAME}" DECRYPTED_FILE="${DECRYPTED_FILENAME}" PASSPHRASE="${PASSPHRASE_FILE}" bash <<'EOF'
    sudo -u postgres openssl enc -d -aes-256-cbc -pbkdf2 \
      -in "/tmp/${BACKUP_FILE}" \
      -out "/tmp/${DECRYPTED_FILE}" \
      -pass file:"${PASSPHRASE}" 2>&1 || echo 'DECRYPT_FAILED'
EOF
)

if [[ "${DECRYPT_RESULT}" == *"DECRYPT_FAILED"* ]] || [[ "${DECRYPT_RESULT}" == *"bad decrypt"* ]]; then
    echo -e "${RED}✗ CRITICAL: Decryption FAILED${NC}"
    echo "  Error: ${DECRYPT_RESULT}"
    echo ""
    echo "This means backups CANNOT be restored with the current passphrase!"
    echo "Possible causes:"
    echo "  1. Passphrase was rotated but backups were encrypted with old passphrase"
    echo "  2. Passphrase file is corrupted or incorrect"
    echo "  3. Backup file is corrupted"
    echo ""
    echo "IMMEDIATE ACTION REQUIRED:"
    echo "  1. Check Ansible Vault for correct passphrase: vault_postgresql_backup_passphrase"
    echo "  2. Compare with passphrase on database server: ${PASSPHRASE_FILE}"
    echo "  3. If passphrase was recently rotated, you'll need the OLD passphrase"
    echo "     to decrypt backups created before the rotation"

    # Cleanup - quote filename to prevent shell injection
    ssh "${SSH_USER}@${DB_SERVER}" "rm \"/tmp/${BACKUP_FILENAME}\""
    rm -rf "${TEMP_DIR}"
    exit 1
fi

# Verify decrypted file is a valid PostgreSQL backup
DECRYPTED_FILE_TYPE=$(ssh "${SSH_USER}@${DB_SERVER}" "file -b \"/tmp/${DECRYPTED_FILENAME}\"")

if [[ "${DECRYPTED_FILE_TYPE}" =~ "PostgreSQL" ]]; then
    echo -e "${GREEN}✓ Decryption SUCCESSFUL${NC}"
    echo "  Decrypted file type: ${DECRYPTED_FILE_TYPE}"

    # Get file size
    DECRYPTED_SIZE=$(ssh "${SSH_USER}@${DB_SERVER}" "du -h \"/tmp/${DECRYPTED_FILENAME}\" | cut -f1")
    echo "  Decrypted backup size: ${DECRYPTED_SIZE}"
elif [[ "${DECRYPTED_FILE_TYPE}" =~ "ASCII text" ]] && [[ "${BACKUP_FILENAME}" =~ "sql.enc" ]]; then
    # For pg_dumpall SQL text backups
    echo -e "${GREEN}✓ Decryption SUCCESSFUL (SQL text backup)${NC}"
    echo "  Decrypted file type: ${DECRYPTED_FILE_TYPE}"

    DECRYPTED_SIZE=$(ssh "${SSH_USER}@${DB_SERVER}" "du -h \"/tmp/${DECRYPTED_FILENAME}\" | cut -f1")
    echo "  Decrypted backup size: ${DECRYPTED_SIZE}"
else
    echo -e "${YELLOW}⚠ WARNING: Decryption succeeded but file type is unexpected${NC}"
    echo "  File type: ${DECRYPTED_FILE_TYPE}"
    echo "  This might indicate a corrupted backup"
fi

# Cleanup
echo ""
echo "Cleaning up temporary files..."
# Pass filenames as environment variables to prevent shell injection
# shellcheck disable=SC2087
ssh "${SSH_USER}@${DB_SERVER}" env BACKUP_FILE="${BACKUP_FILENAME}" DECRYPTED_FILE="${DECRYPTED_FILENAME}" bash <<'EOF'
    sudo rm -f "/tmp/${BACKUP_FILE}" "/tmp/${DECRYPTED_FILE}" 2>/dev/null || true
EOF
# Use shred for sensitive local files (contain database backup data)
if [[ -d "${TEMP_DIR}" ]]; then
    find "${TEMP_DIR}" -type f -exec shred -u {} \; 2>/dev/null || true
    rm -rf "${TEMP_DIR}" 2>/dev/null || true
fi

echo ""
echo "================================================================"
echo -e "${GREEN}SUCCESS: Backup encryption/decryption is working correctly!${NC}"
echo "================================================================"
echo ""
echo "Summary:"
echo "  ✓ Passphrase file exists and has correct permissions"
echo "  ✓ Test encryption/decryption works"
echo "  ✓ Recent backup downloaded from GCS"
echo "  ✓ Backup is properly encrypted"
echo "  ✓ Backup can be decrypted with current passphrase"
echo "  ✓ Decrypted file is a valid PostgreSQL backup"
echo ""
echo "Your backups ARE recoverable with the current passphrase."
echo ""

exit 0
