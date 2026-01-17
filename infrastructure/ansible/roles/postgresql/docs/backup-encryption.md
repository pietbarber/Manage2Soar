# PostgreSQL Multi-Layer Backup Encryption

This document describes the multi-layer encryption strategy for PostgreSQL database backups, including GCS configuration and disaster recovery procedures.

## Table of Contents
- [Security Architecture](#security-architecture)
- [GCS Bucket Setup](#gcs-bucket-setup)
- [Ansible Configuration](#ansible-configuration)
- [Restoration Procedures](#restoration-procedures)
- [Monitoring & Maintenance](#monitoring--maintenance)

## Security Architecture

### Layer 1: Client-Side Encryption (CRITICAL)
**OpenSSL AES-256-CBC encryption before upload to GCS**

- Encryption happens on the database server **before** any data leaves the VM
- Uses AES-256-CBC with PBKDF2 key derivation
- Passphrase stored in Ansible Vault: `vault_postgresql_backup_passphrase`
- Deployed to database server at `/root/.backup_passphrase` (mode `0400`, owner `root`)
- Passphrase is 64+ character random string
- **Result**: Even with GCS bucket access, attackers get AES-256 encrypted blobs

### Layer 2: GCS Server-Side Encryption
**Customer-Managed Encryption Keys (CMEK) via Cloud KMS**

- Cloud KMS keyring for backup encryption
- Keys never leave Google's infrastructure
- Automatic key rotation support (recommended: 90 days)
- Access controlled via IAM roles
- **Result**: Second layer of encryption managed by Google Cloud KMS

### Layer 3: GCS Bucket Hardening
**Strict access controls and security configuration**

- Private bucket (no public access, no `allUsers`/`allAuthenticatedUsers`)
- IAM: Database server service account has **write-only** access (`storage.objects.create`)
- Object lifecycle policy: Move to Coldline storage after 30 days (cost optimization)
- Versioning enabled (protect against accidental deletion)
- Audit logging enabled (Cloud Audit Logs)
- Uniform bucket-level access (no object ACLs)
- **Result**: Even if service account credentials leak, attacker can only upload (not read/delete)

## GCS Bucket Setup

### Prerequisites

- Google Cloud project (e.g., `skyline-soaring-storage`)
- `gcloud` CLI installed and authenticated
- Appropriate IAM permissions to create KMS keys and GCS buckets

### Step 1: Create Cloud KMS Keyring and Key

```bash
# Create KMS keyring in us-east1 (match your GCS bucket location)
gcloud kms keyrings create m2s-backups \
  --location=us-east1 \
  --project=skyline-soaring-storage

# Create encryption key with 90-day rotation
gcloud kms keys create database-backups \
  --keyring=m2s-backups \
  --location=us-east1 \
  --purpose=encryption \
  --rotation-period=90d \
  --project=skyline-soaring-storage

# Grant Cloud KMS CryptoKey Encrypter/Decrypter role to GCS service account
# This allows GCS to use the key for encryption/decryption
PROJECT_NUMBER=$(gcloud projects describe skyline-soaring-storage --format="value(projectNumber)")
GCS_SERVICE_ACCOUNT="service-${PROJECT_NUMBER}@gs-project-accounts.iam.gserviceaccount.com"

gcloud kms keys add-iam-policy-binding database-backups \
  --keyring=m2s-backups \
  --location=us-east1 \
  --member="serviceAccount:${GCS_SERVICE_ACCOUNT}" \
  --role=roles/cloudkms.cryptoKeyEncrypterDecrypter \
  --project=skyline-soaring-storage
```

### Step 2: Create GCS Bucket with CMEK

```bash
# Create bucket with uniform bucket-level access and public access prevention
gcloud storage buckets create gs://m2s-database-backups \
  --location=us-east1 \
  --uniform-bucket-level-access \
  --public-access-prevention=enforced \
  --project=skyline-soaring-storage

# Configure CMEK encryption
gcloud storage buckets update gs://m2s-database-backups \
  --default-encryption-key=projects/skyline-soaring-storage/locations/us-east1/keyRings/m2s-backups/cryptoKeys/database-backups

# Enable versioning for accidental deletion protection
gcloud storage buckets update gs://m2s-database-backups \
  --versioning
```

### Step 3: Configure Lifecycle Policy

Create `lifecycle.json`:

```json
{
  "lifecycle": {
    "rule": [
      {
        "action": {
          "type": "SetStorageClass",
          "storageClass": "COLDLINE"
        },
        "condition": {
          "age": 30,
          "matchesPrefix": ["postgresql/"]
        }
      },
      {
        "action": {
          "type": "Delete"
        },
        "condition": {
          "age": 365,
          "matchesPrefix": ["postgresql/"]
        }
      }
    ]
  }
}
```

Apply lifecycle policy:

```bash
gcloud storage buckets update gs://m2s-database-backups \
  --lifecycle-file=lifecycle.json
```

**Policy Details:**
- After 30 days: Move to Coldline storage (cheaper, but retrieval costs)
- After 365 days: Delete backups (adjust retention period as needed)
- Only applies to `postgresql/` prefix

### Step 4: Configure IAM for Database Server

```bash
# Create service account for database server (if not exists)
gcloud iam service-accounts create m2s-database-backup \
  --display-name="M2S Database Backup Uploader" \
  --project=skyline-soaring-storage

# Grant WRITE-ONLY access to GCS bucket
gcloud storage buckets add-iam-policy-binding gs://m2s-database-backups \
  --member="serviceAccount:m2s-database-backup@skyline-soaring-storage.iam.gserviceaccount.com" \
  --role=roles/storage.objectCreator

# Download service account key for database server
gcloud iam service-accounts keys create ~/m2s-database-backup-key.json \
  --iam-account=m2s-database-backup@skyline-soaring-storage.iam.gserviceaccount.com \
  --project=skyline-soaring-storage

# Copy key to database server (secure transfer)
scp ~/m2s-database-backup-key.json pb@DATABASE_SERVER_IP:/tmp/
ssh pb@DATABASE_SERVER_IP "sudo mv /tmp/m2s-database-backup-key.json /root/.gcs-backup-key.json && sudo chmod 400 /root/.gcs-backup-key.json"

# Activate service account on database server
ssh pb@DATABASE_SERVER_IP "sudo gcloud auth activate-service-account --key-file=/root/.gcs-backup-key.json"

# Remove local copy
rm ~/m2s-database-backup-key.json
```

### Step 5: Verify Configuration

```bash
# Verify KMS key exists
gcloud kms keys describe database-backups \
  --keyring=m2s-backups \
  --location=us-east1 \
  --project=skyline-soaring-storage

# Verify bucket configuration
gcloud storage buckets describe gs://m2s-database-backups --format=json

# Test upload from database server
ssh pb@DATABASE_SERVER_IP "echo 'test' | sudo gsutil cp - gs://m2s-database-backups/postgresql/test.txt"
ssh pb@DATABASE_SERVER_IP "sudo gsutil ls gs://m2s-database-backups/postgresql/"

# Clean up test file
ssh pb@DATABASE_SERVER_IP "sudo gsutil rm gs://m2s-database-backups/postgresql/test.txt"
```

## Ansible Configuration

### Step 1: Generate Encryption Passphrase

```bash
# Generate 64-character random passphrase
openssl rand -base64 48

# Output example: "8fJ9k2L4m6N8p0Q2r4S6t8U0v2W4x6Y8z0A2b4C6d8E0f2G4h6I8j0K2"
```

### Step 2: Add Passphrase to Ansible Vault

Edit vault file (e.g., `group_vars/gcp_database/vault.yml`):

```bash
ansible-vault edit --vault-password-file ~/.ansible_vault_pass group_vars/gcp_database/vault.yml
```

Add:

```yaml
vault_postgresql_backup_passphrase: "YOUR_64_CHAR_PASSPHRASE_HERE"
```

### Step 3: Configure Variables

Edit `group_vars/gcp_database/vars.yml`:

```yaml
# Enable GCS backup with encryption
postgresql_backup_gcs_enabled: true
postgresql_backup_gcs_bucket: "m2s-database-backups"
postgresql_backup_encryption_enabled: true

# GCS lifecycle settings
postgresql_backup_gcs_coldline_days: 30
postgresql_backup_gcs_delete_days: 365  # 1 year retention

# Local backup retention (keep 7 days locally)
postgresql_backup_retention_days: 7
```

### Step 4: Deploy Configuration

```bash
cd infrastructure/ansible

# Deploy PostgreSQL role with backup configuration
ansible-playbook -i inventory/gcp_database.yml playbooks/gcp-database.yml \
  --tags postgresql,backup

# Verify deployment
ansible -i inventory/gcp_database.yml gcp_database -m shell \
  -a "ls -lh /root/.backup_passphrase" --become

ansible -i inventory/gcp_database.yml gcp_database -m shell \
  -a "ls -lh /usr/local/bin/m2s-pg-backup.sh" --become
```

### Step 5: Test Backup

```bash
# Run backup manually
ansible -i inventory/gcp_database.yml gcp_database -m shell \
  -a "/usr/local/bin/m2s-pg-backup.sh" --become -u postgres

# Check local backup directory
ansible -i inventory/gcp_database.yml gcp_database -m shell \
  -a "ls -lh /var/backups/postgresql/daily/" --become

# Check GCS bucket
ansible -i inventory/gcp_database.yml gcp_database -m shell \
  -a "gsutil ls gs://m2s-database-backups/postgresql/" --become
```

## Restoration Procedures

### Scenario 1: Restore from Local Encrypted Backup

**Use Case**: Database server is still accessible, need to restore from recent backup

```bash
# 1. List available local backups
ssh pb@DATABASE_SERVER_IP "sudo ls -lh /var/backups/postgresql/daily/"

# 2. Choose backup to restore (replace TIMESTAMP with actual value)
BACKUP_TIMESTAMP="2026-01-16_020000"

# 3. Decrypt backup on database server
ssh pb@DATABASE_SERVER_IP "sudo openssl enc -d -aes-256-cbc -pbkdf2 \
  -in /var/backups/postgresql/daily/m2s_${BACKUP_TIMESTAMP}.pgdump.enc \
  -out /tmp/m2s_restore.pgdump \
  -pass file:/root/.backup_passphrase"

# 4. Verify decrypted backup
ssh pb@DATABASE_SERVER_IP "sudo file /tmp/m2s_restore.pgdump"
# Expected output: PostgreSQL custom database dump

# 5. Drop existing database (WARNING: DATA LOSS)
ssh pb@DATABASE_SERVER_IP "sudo -u postgres psql -c 'DROP DATABASE m2s;'"

# 6. Create fresh database
ssh pb@DATABASE_SERVER_IP "sudo -u postgres psql -c 'CREATE DATABASE m2s OWNER m2s;'"

# 7. Restore from backup
ssh pb@DATABASE_SERVER_IP "sudo -u postgres pg_restore -d m2s /tmp/m2s_restore.pgdump"

# 8. Clean up decrypted file
ssh pb@DATABASE_SERVER_IP "sudo rm -f /tmp/m2s_restore.pgdump"

# 9. Restart application
# For single-host: sudo systemctl restart gunicorn
# For GKE: kubectl rollout restart deployment/m2s-deployment
```

### Scenario 2: Restore from GCS (Disaster Recovery)

**Use Case**: Database server failed, need to restore from GCS to new server

```bash
# 1. List available GCS backups
gsutil ls gs://m2s-database-backups/postgresql/

# 2. Download encrypted backup (replace TIMESTAMP)
BACKUP_TIMESTAMP="2026-01-16_020000"
gsutil cp "gs://m2s-database-backups/postgresql/m2s_${BACKUP_TIMESTAMP}.pgdump.enc" /tmp/

# 3. Retrieve passphrase from Ansible Vault
ansible-vault view --vault-password-file ~/.ansible_vault_pass \
  group_vars/gcp_database/vault.yml | \
  grep vault_postgresql_backup_passphrase | \
  cut -d':' -f2 | \
  tr -d ' ' > /tmp/passphrase.txt

chmod 600 /tmp/passphrase.txt

# 4. Decrypt backup
openssl enc -d -aes-256-cbc -pbkdf2 \
  -in /tmp/m2s_${BACKUP_TIMESTAMP}.pgdump.enc \
  -out /tmp/m2s_restore.pgdump \
  -pass file:/tmp/passphrase.txt

# 5. Verify decrypted backup
file /tmp/m2s_restore.pgdump
# Expected output: PostgreSQL custom database dump

# 6. Copy to new database server
scp /tmp/m2s_restore.pgdump pb@NEW_DATABASE_SERVER:/tmp/

# 7. Restore database on new server
ssh pb@NEW_DATABASE_SERVER "sudo -u postgres createdb m2s -O m2s"
ssh pb@NEW_DATABASE_SERVER "sudo -u postgres pg_restore -d m2s /tmp/m2s_restore.pgdump"

# 8. Clean up sensitive files
rm -f /tmp/passphrase.txt /tmp/m2s_${BACKUP_TIMESTAMP}.pgdump.enc /tmp/m2s_restore.pgdump
ssh pb@NEW_DATABASE_SERVER "sudo rm -f /tmp/m2s_restore.pgdump"

# 9. Update application connection strings to new database server
# Update Ansible inventory and redeploy
```

### Scenario 3: Partial Restore (Single Table)

**Use Case**: Need to restore specific table(s) without full database restore

```bash
# 1. Download and decrypt backup (steps 1-4 from Scenario 2)

# 2. List available tables in backup
pg_restore -l /tmp/m2s_restore.pgdump | grep TABLE

# 3. Restore specific table (example: members_member)
pg_restore -d m2s -t members_member /tmp/m2s_restore.pgdump

# 4. Verify restore
psql -d m2s -c "SELECT COUNT(*) FROM members_member;"

# 5. Clean up
rm -f /tmp/m2s_restore.pgdump
```

## Monitoring & Maintenance

### Backup Monitoring

```bash
# Check backup cron job status
ssh pb@DATABASE_SERVER_IP "sudo systemctl status cron"

# View recent backup logs
ssh pb@DATABASE_SERVER_IP "sudo tail -50 /var/log/m2s-pg-backup.log"

# Check local backup count and sizes
ssh pb@DATABASE_SERVER_IP "sudo du -sh /var/backups/postgresql/daily/*"

# Check GCS backup count
gsutil ls -lh gs://m2s-database-backups/postgresql/ | tail -10

# Verify latest backup is encrypted
ssh pb@DATABASE_SERVER_IP "sudo file /var/backups/postgresql/daily/m2s_latest.enc"
# Expected output: "data" (encrypted binary)
```

### Key Rotation

**Rotate Encryption Passphrase** (every 6-12 months):

```bash
# 1. Generate new passphrase
NEW_PASSPHRASE=$(openssl rand -base64 48)

# 2. Update Ansible Vault
ansible-vault edit --vault-password-file ~/.ansible_vault_pass \
  group_vars/gcp_database/vault.yml

# Replace vault_postgresql_backup_passphrase with new value

# 3. Redeploy backup configuration
ansible-playbook -i inventory/gcp_database.yml playbooks/gcp-database.yml \
  --tags postgresql,backup

# 4. Test backup with new passphrase
ansible -i inventory/gcp_database.yml gcp_database -m shell \
  -a "/usr/local/bin/m2s-pg-backup.sh" --become -u postgres

# 5. Old backups remain encrypted with old passphrase
# Document old passphrase for disaster recovery until old backups expire
```

**Cloud KMS Key Rotation** (automatic with 90-day period):

- Cloud KMS automatically creates new versions every 90 days
- Old key versions remain available for decryption
- No manual action required
- Verify rotation schedule:

```bash
gcloud kms keys describe database-backups \
  --keyring=m2s-backups \
  --location=us-east1 \
  --project=skyline-soaring-storage
```

### Cost Optimization

**Storage Costs** (as of 2026):

- Standard storage (0-30 days): $0.023/GB/month
- Coldline storage (30+ days): $0.006/GB/month
- Retrieval from Coldline: $0.02/GB
- Network egress: $0.12/GB

**Example**: 50GB database, daily backups, 365-day retention

- Daily backups for 30 days: 50GB × 30 × $0.023 = $34.50/month
- Coldline backups 30-365 days: 50GB × 335 × $0.006 = $100.50/month
- **Total**: ~$135/month storage cost

**Optimization Tips**:

1. Adjust `postgresql_backup_gcs_delete_days` based on compliance requirements
2. Consider weekly backups instead of daily after 30 days
3. Use GCS lifecycle policies to automatically delete old backups
4. Monitor actual database size growth and adjust retention accordingly

### Security Auditing

```bash
# Check GCS bucket IAM policy
gcloud storage buckets get-iam-policy gs://m2s-database-backups

# Check Cloud KMS key IAM policy
gcloud kms keys get-iam-policy database-backups \
  --keyring=m2s-backups \
  --location=us-east1 \
  --project=skyline-soaring-storage

# View GCS audit logs
gcloud logging read "resource.type=gcs_bucket \
  AND resource.labels.bucket_name=m2s-database-backups" \
  --limit=50 \
  --format=json
```

## Troubleshooting

### Encryption Fails

```bash
# Check passphrase file exists and has correct permissions
ssh pb@DATABASE_SERVER_IP "sudo ls -lh /root/.backup_passphrase"
# Expected: -r-------- 1 root root 65 /root/.backup_passphrase

# Test OpenSSL encryption manually
ssh pb@DATABASE_SERVER_IP "echo 'test' | sudo openssl enc -aes-256-cbc -salt -pbkdf2 \
  -pass file:/root/.backup_passphrase | sudo openssl enc -d -aes-256-cbc -pbkdf2 \
  -pass file:/root/.backup_passphrase"
# Expected output: "test"
```

### GCS Upload Fails

```bash
# Check service account authentication
ssh pb@DATABASE_SERVER_IP "sudo gcloud auth list"

# Test GCS write access
ssh pb@DATABASE_SERVER_IP "echo 'test' | sudo gsutil cp - gs://m2s-database-backups/postgresql/test.txt"

# Check network connectivity
ssh pb@DATABASE_SERVER_IP "curl -I https://storage.googleapis.com"

# Verify IAM permissions
gcloud storage buckets get-iam-policy gs://m2s-database-backups | grep m2s-database-backup
```

### Decryption Fails

```bash
# Verify backup is encrypted
file backup.pgdump.enc
# Expected output: "data" (not "PostgreSQL custom database dump")

# Check passphrase is correct
openssl enc -d -aes-256-cbc -pbkdf2 \
  -in backup.pgdump.enc \
  -out /dev/null \
  -pass file:/root/.backup_passphrase
# Should complete without errors

# Try decryption with verbose output
openssl enc -d -aes-256-cbc -pbkdf2 -v \
  -in backup.pgdump.enc \
  -out test_restore.pgdump \
  -pass file:/root/.backup_passphrase
```

## Security Best Practices

1. **Never store unencrypted backups in GCS** - Always enable `postgresql_backup_encryption_enabled`
2. **Rotate passphrases annually** - Schedule key rotation in security calendar
3. **Document disaster recovery procedures** - Test restoration quarterly
4. **Limit GCS service account permissions** - Write-only access prevents data exfiltration
5. **Enable GCS versioning** - Protects against accidental deletion
6. **Monitor backup success** - Set up alerts for backup failures
7. **Test restoration regularly** - Verify backups are usable before disaster strikes
8. **Secure passphrase access** - Only store in Ansible Vault, never in plaintext

## References

- [Google Cloud KMS Documentation](https://cloud.google.com/kms/docs)
- [GCS Customer-Managed Encryption Keys](https://cloud.google.com/storage/docs/encryption/customer-managed-keys)
- [OpenSSL Encryption](https://www.openssl.org/docs/man1.1.1/man1/enc.html)
- [PostgreSQL pg_dump Documentation](https://www.postgresql.org/docs/current/app-pgdump.html)
- [PostgreSQL pg_restore Documentation](https://www.postgresql.org/docs/current/app-pgrestore.html)
