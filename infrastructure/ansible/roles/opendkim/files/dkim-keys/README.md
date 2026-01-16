# DKIM Key Storage

This directory contains DKIM private and public keys for all domains served by the mail server.

## Directory Structure

```
dkim-keys/
├── skylinesoaring.org/
│   ├── m2s.private  (Ansible Vault encrypted - GITIGNORED)
│   └── m2s.txt      (Public key - GITIGNORED)
├── ssc.manage2soar.com/
│   ├── m2s.private  (Ansible Vault encrypted - GITIGNORED)
│   └── m2s.txt      (Public key - GITIGNORED)
└── masa.manage2soar.com/
    ├── m2s.private  (Ansible Vault encrypted - GITIGNORED)
    └── m2s.txt      (Public key - GITIGNORED)
```

## Security

- **ALL KEYS ARE GITIGNORED** - Keys are never committed to the repository for security
- **Private keys** (`m2s.private`) are encrypted with Ansible Vault using the vault password in `~/.ansible_vault_pass`
- **Public keys** (`m2s.txt`) contain the public DKIM key portion
- Keys are deployed to the mail server at `/etc/opendkim/keys/{domain}/` with proper ownership (opendkim:opendkim) and permissions (0600 for private, 0644 for public)

## Hybrid Deployment Strategy

The OpenDKIM role uses a **smart fallback approach**:

1. **First**: Check if keys exist in `roles/opendkim/files/dkim-keys/{domain}/`
2. **If found**: Deploy keys from Ansible (decrypt vault-encrypted files)
3. **If NOT found**: Generate new keys on the mail server (original behavior)

This supports three use cases:
- ✅ **Your deployment**: Keys in local files, deployed from Ansible (IaC-first)
- ✅ **Fresh installation**: No keys in files, auto-generate on first run
- ✅ **Other clubs**: Clone repository, run playbook, keys generated automatically

## Backup Strategy (Option 4 - Hybrid)

### Primary: Ansible Vault (IaC)
- Keys stored in this directory, encrypted with Ansible Vault
- Version controlled in git repository
- Deployed automatically by OpenDKIM Ansible role
- Source of truth for all DKIM keys

### Secondary: GCS Backup (Disaster Recovery)
- Optional automated backup to Google Cloud Storage
- Triggered during Ansible playbook runs when `gcs_backup_bucket` variable is defined
- Double encryption: OpenSSL AES-256-CBC + GCS CMEK (if configured)
- Stored as timestamped archives: `gs://{bucket}/dkim-keys/dkim-keys-{timestamp}.tar.gz.enc`

## Key Management Operations

### Viewing Private Keys
```bash
# From Ansible control node
cd infrastructure/ansible/roles/opendkim/files/dkim-keys
ansible-vault view --vault-password-file ~/.ansible_vault_pass skylinesoaring.org/m2s.private
```

### Adding New Domain Keys
```bash
# 1. Generate keys on mail server (or use opendkim-genkey locally)
ssh mail-server "sudo opendkim-genkey -b 2048 -d newdomain.com -s m2s -D /tmp/"

# 2. Pull keys to Ansible
mkdir -p roles/opendkim/files/dkim-keys/newdomain.com
scp mail-server:/tmp/m2s.private roles/opendkim/files/dkim-keys/newdomain.com/
scp mail-server:/tmp/m2s.txt roles/opendkim/files/dkim-keys/newdomain.com/

# 3. Encrypt private key
ansible-vault encrypt --vault-password-file ~/.ansible_vault_pass \
  roles/opendkim/files/dkim-keys/newdomain.com/m2s.private

# 4. Add domain to group_vars/gcp_mail/vars.yml
#    Either club_domains or dkim_additional_domains

# 5. Commit to git and redeploy
git add roles/opendkim/files/dkim-keys/newdomain.com/
git commit -m "Add DKIM keys for newdomain.com"
ansible-playbook -i inventory/gcp_mail.yml playbooks/gcp-mail-server.yml --tags opendkim
```

### Rotating Keys
```bash
# 1. Generate new keys
opendkim-genkey -b 2048 -d domain.com -s m2s-new -D /tmp/

# 2. Update DNS with new selector (m2s-new._domainkey.domain.com)

# 3. Wait for DNS propagation (24-48 hours for safety)

# 4. Replace old keys in Ansible with new keys

# 5. Update dkim_selector in group_vars from "m2s" to "m2s-new"

# 6. Redeploy with Ansible
```

### Restoring from GCS Backup
```bash
# 1. List available backups
gsutil ls gs://{bucket}/dkim-keys/

# Output will show timestamped files like:
# gs://{bucket}/dkim-keys/dkim-keys-20260116T235900.tar.gz.enc
# gs://{bucket}/dkim-keys/dkim-keys-20260115T120000.tar.gz.enc
# Choose the timestamp you want to restore

# 2. Download encrypted backup (replace {timestamp} with actual value)
gsutil cp gs://{bucket}/dkim-keys/dkim-keys-{timestamp}.tar.gz.enc /tmp/

# 3. Decrypt backup
# Option A: Use the vault variable directly (requires vault password)
ansible-vault view --vault-password-file ~/.ansible_vault_pass group_vars/gcp_mail/vault.yml | \
  grep vault_dkim_backup_encryption_key | \
  cut -d':' -f2 | \
  xargs -I {} openssl enc -d -aes-256-cbc -pbkdf2 \
    -in /tmp/dkim-keys-{timestamp}.tar.gz.enc \
    -out /tmp/dkim-keys.tar.gz \
    -pass pass:{}

# Option B: Manually provide the password
openssl enc -d -aes-256-cbc -pbkdf2 \
  -in /tmp/dkim-keys-{timestamp}.tar.gz.enc \
  -out /tmp/dkim-keys.tar.gz \
  -pass pass:"your-encryption-password-here"

# 4. Extract keys
mkdir -p /tmp/dkim-restore/
tar xzf /tmp/dkim-keys.tar.gz -C /tmp/dkim-restore/

# 5. Encrypt with Ansible Vault and move to repository
find /tmp/dkim-restore/ -mindepth 1 -maxdepth 1 -type d -print0 | while IFS= read -r -d '' domain_dir; do
  domain_name=$(basename "$domain_dir")
  mkdir -p "roles/opendkim/files/dkim-keys/$domain_name"
  cp "$domain_dir/m2s.txt" "roles/opendkim/files/dkim-keys/$domain_name/"
  ansible-vault encrypt --vault-password-file ~/.ansible_vault_pass \
    --output "roles/opendkim/files/dkim-keys/$domain_name/m2s.private" \
    "$domain_dir/m2s.private"
done
```

## DNS Configuration

After deploying keys, add these DNS records for each domain:

**DKIM Record:**
- Type: TXT
- Name: `m2s._domainkey`
- Value: (content of `m2s.txt` file, remove comments and format as single line)

**SPF Record:**
- Type: TXT
- Name: `@`
- Value: `v=spf1 include:spf.smtp2go.com ~all`

**DMARC Record:**
- Type: TXT
- Name: `_dmarc`
- Value (initial monitoring): `v=DMARC1; p=none; rua=mailto:dmarc@{domain}`

**DMARC Policy Progression:**
Start with `p=none` in production to monitor DMARC aggregate reports without affecting delivery. Verify that all legitimate email has correct SPF/DKIM alignment. After 1-4 weeks of monitoring and fixing any issues, gradually move to stricter policies:

- **Monitoring** (start here): `v=DMARC1; p=none; rua=mailto:dmarc@{domain}`
- **Quarantine** (after verification): `v=DMARC1; p=quarantine; rua=mailto:dmarc@{domain}`
- **Reject** (production hardened): `v=DMARC1; p=reject; rua=mailto:dmarc@{domain}`

## Related Documentation

- [Issue #504](https://github.com/pietbarber/Manage2Soar/issues/504) - DKIM Multi-Domain Support
- [Issue #500](https://github.com/pietbarber/Manage2Soar/issues/500) - Database Backup Encryption (similar strategy)
- [Pre-Golive Checklist](../../../../../docs/pre-golive-checklist.md) - Email authentication setup
