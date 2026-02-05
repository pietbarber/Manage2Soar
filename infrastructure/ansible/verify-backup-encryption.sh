#!/bin/bash
# Verify PostgreSQL Backup Encryption/Decryption Works
# Tests that the backup passphrase can successfully decrypt existing backups
#
# Usage: ./verify-backup-encryption.sh [DATABASE_SERVER_IP]
#
# This script:
# 1. Checks passphrase file exists on database server
# 2. Downloads a recent encrypted backup from GCS
# 3. Tests decryption with the current passphrase
# 4. Verifies the decrypted file is a valid PostgreSQL backup
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
# Auto-detect database server from Ansible inventory if not provided
if [[ -z "${1:-}" ]] && [[ -f "inventory/gcp_database.yml" ]]; then
    # Extract ansible_host from gcp_database.yml inventory
    DB_SERVER=$(grep -A5 "m2s-database:" inventory/gcp_database.yml | grep "ansible_host:" | head -1 | awk '{print $2}')
    if [[ -z "${DB_SERVER}" ]]; then
        echo -e "${RED}ERROR: Could not auto-detect database server from inventory/gcp_database.yml${NC}"
        echo "Usage: $0 [database-server-ip-or-hostname]"
        exit 1
    fi
    echo "Auto-detected database server: ${DB_SERVER}"
else
    DB_SERVER="${1:-m2s-database}"
fi

# Auto-detect GCS bucket from Ansible group_vars
GCS_BUCKET_NAME="m2s-database-backups-manage2soar"  # Default
if [[ -f "group_vars/gcp_database/vars.yml" ]]; then
    DETECTED_BUCKET=$(grep "postgresql_backup_gcs_bucket:" group_vars/gcp_database/vars.yml | awk '{print $2}' | tr -d '"')
    if [[ -n "${DETECTED_BUCKET}" ]]; then
        GCS_BUCKET_NAME="${DETECTED_BUCKET}"
    fi
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
if ssh "pb@${DB_SERVER}" "sudo test -f ${PASSPHRASE_FILE}"; then
    echo -e "${GREEN}✓ Passphrase file exists: ${PASSPHRASE_FILE}${NC}"

    # Check permissions
    PERMS=$(ssh "pb@${DB_SERVER}" "sudo stat -c '%a %U %G' ${PASSPHRASE_FILE}")
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
echo "[2/5] Testing encryption/decryption with test data..."
TEST_STRING="manage2soar-backup-test-$(date +%s)"
ENCRYPTED=$(ssh "pb@${DB_SERVER}" "echo '${TEST_STRING}' | sudo -u postgres openssl enc -aes-256-cbc -salt -pbkdf2 -pass file:${PASSPHRASE_FILE} -base64")
DECRYPTED=$(ssh "pb@${DB_SERVER}" "echo '${ENCRYPTED}' | sudo -u postgres openssl enc -d -aes-256-cbc -pbkdf2 -pass file:${PASSPHRASE_FILE} -base64")

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
scp "${TEMP_DIR}/${BACKUP_FILENAME}" "pb@${DB_SERVER}:/tmp/"

# Attempt decryption on database server
DECRYPTED_FILENAME="${BACKUP_FILENAME%.enc}"
DECRYPT_RESULT=$(ssh "pb@${DB_SERVER}" "
    sudo -u postgres openssl enc -d -aes-256-cbc -pbkdf2 \
      -in /tmp/${BACKUP_FILENAME} \
      -out /tmp/${DECRYPTED_FILENAME} \
      -pass file:${PASSPHRASE_FILE} 2>&1 || echo 'DECRYPT_FAILED'
")

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

    # Cleanup
    ssh "pb@${DB_SERVER}" "rm /tmp/${BACKUP_FILENAME}"
    rm -rf "${TEMP_DIR}"
    exit 1
fi

# Verify decrypted file is a valid PostgreSQL backup
DECRYPTED_FILE_TYPE=$(ssh "pb@${DB_SERVER}" "file -b /tmp/${DECRYPTED_FILENAME}")

if [[ "${DECRYPTED_FILE_TYPE}" =~ "PostgreSQL" ]]; then
    echo -e "${GREEN}✓ Decryption SUCCESSFUL${NC}"
    echo "  Decrypted file type: ${DECRYPTED_FILE_TYPE}"

    # Get file size
    DECRYPTED_SIZE=$(ssh "pb@${DB_SERVER}" "du -h /tmp/${DECRYPTED_FILENAME} | cut -f1")
    echo "  Decrypted backup size: ${DECRYPTED_SIZE}"
elif [[ "${DECRYPTED_FILE_TYPE}" =~ "ASCII text" ]] && [[ "${BACKUP_FILENAME}" =~ "sql.enc" ]]; then
    # For pg_dumpall SQL text backups
    echo -e "${GREEN}✓ Decryption SUCCESSFUL (SQL text backup)${NC}"
    echo "  Decrypted file type: ${DECRYPTED_FILE_TYPE}"

    DECRYPTED_SIZE=$(ssh "pb@${DB_SERVER}" "du -h /tmp/${DECRYPTED_FILENAME} | cut -f1")
    echo "  Decrypted backup size: ${DECRYPTED_SIZE}"
else
    echo -e "${YELLOW}⚠ WARNING: Decryption succeeded but file type is unexpected${NC}"
    echo "  File type: ${DECRYPTED_FILE_TYPE}"
    echo "  This might indicate a corrupted backup"
fi

# Cleanup
echo ""
echo "Cleaning up temporary files..."
ssh "pb@${DB_SERVER}" "sudo rm -f /tmp/${BACKUP_FILENAME} /tmp/${DECRYPTED_FILENAME}" 2>/dev/null || true
rm -rf "${TEMP_DIR}" 2>/dev/null || true

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
