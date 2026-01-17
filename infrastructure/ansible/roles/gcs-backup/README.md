---
# GCS Backup Role

Provisions Google Cloud Storage bucket with KMS encryption for PostgreSQL database backups.

## Purpose

This role provisions the cloud infrastructure required for encrypted database backups:
- Cloud KMS keyring and encryption key with automatic 90-day rotation
- GCS bucket with CMEK (Customer-Managed Encryption Key) default encryption
- Public Access Prevention (enforced private bucket)
- Bucket versioning for accidental deletion protection
- Optional lifecycle policy (transition to Coldline storage, then deletion)
- IAM bindings for GCS service account and VM service account

## Prerequisites

- `gcloud` CLI installed and authenticated on localhost
- Appropriate GCP permissions to create KMS keys, GCS buckets, and IAM bindings
- `google.cloud` Ansible collection (see `galaxy-requirements.yml`)

## Required Variables

- `gcs_backup_project`: GCP project ID where resources will be created
- `gcs_backup_location`: GCP region (e.g., `us-east1`)
- `gcs_backup_bucket`: Bucket name (must be globally unique)
- `gcs_backup_kms_keyring`: KMS keyring name
- `gcs_backup_kms_key`: KMS key name
- `gcs_backup_vm_service_account`: Service account email for VM uploading backups (e.g., `<project-number>-compute@developer.gserviceaccount.com`)

## Optional Variables

- `gcs_backup_storage_class`: GCS storage class (default: `STANDARD`)
- `gcs_backup_kms_rotation_period`: KMS key rotation period (default: `90d`)
- `gcs_backup_kms_next_rotation_time`: Explicit next rotation timestamp (ISO 8601 format)
- `gcs_backup_coldline_days`: Days before transitioning to Coldline storage (default: `30`)
- `gcs_backup_delete_days`: Days before deleting old backups (default: `365`)
- `gcp_auth_kind`: GCP authentication method (default: `application`)
- `gcp_service_account_file`: Path to service account key file (optional)

## Example Usage

### 1. Create vars file from example

```bash
cp infrastructure/ansible/group_vars/gcp_backup.vars.yml.example infrastructure/ansible/group_vars/gcs_backup/vars.yml
```

### 2. Edit vars file with your environment-specific values

```yaml
---
gcs_backup_project: "your-project-id"
gcs_backup_location: "us-east1"
gcs_backup_bucket: "your-backups-bucket-name"
gcs_backup_kms_keyring: "your-backups-keyring"
gcs_backup_kms_key: "database-backups"
gcs_backup_vm_service_account: "123456789-compute@developer.gserviceaccount.com"
```

### 3. Run the provisioning playbook

```bash
cd infrastructure/ansible
ansible-playbook playbooks/gcp-backup-storage.yml
```

## Idempotency Guarantees

This role is fully idempotent and safe to run multiple times:

- **KMS keyring/key**: Only created if they don't exist
- **GCS bucket**: Only created if it doesn't exist (using `google.cloud.gcp_storage_bucket` module)
- **Public Access Prevention**: Only enforced if not already set
- **CMEK encryption**: Only applied if default key doesn't match
- **Bucket versioning**: Only enabled if not already enabled
- **Lifecycle policy**: Only applied if rules don't match current configuration
- **IAM bindings**: Only added if member doesn't already have the role

All tasks check existing state before making changes, ensuring Ansible reports accurate change status.

## Integration with PostgreSQL Backup System

This role provisions the infrastructure that the `postgresql` role's backup script uses:

1. **Two-layer encryption**:
   - Layer 1: Client-side OpenSSL AES-256-CBC encryption (handled by backup script)
   - Layer 2: Server-side CMEK encryption via Cloud KMS (handled by this role)

2. **IAM permissions**:
   - VM service account: `roles/storage.objectCreator` (write-only bucket access)
   - GCS service account: `roles/cloudkms.cryptoKeyEncrypterDecrypter` (CMEK encryption/decryption)

3. **Lifecycle management**:
   - Backups transition to Coldline storage after `gcs_backup_coldline_days` (cost optimization)
   - Automatic deletion after `gcs_backup_delete_days` (compliance/retention policy)

## Security Hardening

- Bucket has uniform bucket-level access (no legacy ACLs)
- Public Access Prevention enforced (prevents accidental public exposure)
- Write-only access for backup VM (principle of least privilege)
- KMS key rotation every 90 days (defense in depth)
- Bucket versioning enabled (protection against accidental deletion)

## Dependencies

This role requires the `google.cloud` Ansible collection. Install via:

```bash
ansible-galaxy collection install -r galaxy-requirements.yml
```

See `galaxy-requirements.yml` for specific version requirements.
