# Ansible Playbook Guide

Complete reference for all Ansible playbooks used in Manage2Soar infrastructure management.

## 📖 Overview

This guide documents all Ansible playbooks in `infrastructure/ansible/playbooks/`, their purpose, usage patterns, and common scenarios. Always refer to this guide before manual operations - IaC-first approach.

## 🔐 Vault Architecture: One Vault To Rule Them All

**IMPORTANT**: All production secrets are stored in a **single master vault file**:

```
infrastructure/ansible/group_vars/localhost/vault.yml  ← MASTER VAULT
```

Other vault locations are **symlinks** to this master file:
- `group_vars/gcp_app/vault.yml` → symlink to `localhost/vault.yml`
- `group_vars/gcp_provisioner/vault.yml` → symlink to `localhost/vault.yml`

**Specialized vaults** (different structure/password):
- `group_vars/gcp_mail/vault.yml` - SMTP2Go API credentials (different structure)
- `group_vars/single_host/vault.yml` - Dev/test environment (different password)

**WHY**: Single source of truth prevents drift, simplifies secret management, enforces IaC-first philosophy. All production secrets are synchronized with K8s secrets.

## 🗂️ Playbook Index

| Playbook | Purpose | Frequency | Tags |
|----------|---------|-----------|------|
| [gcp-app-deploy.yml](#gcp-app-deployyml) | Deploy Django app to GKE | Weekly | `secrets`, `build`, `deploy` |
| [gcp-database.yml](#gcp-databaseyml) | Provision/configure PostgreSQL | Monthly | `gcp-provision`, `postgresql`, `ssl` |
| [gcp-cluster-provision.yml](#gcp-cluster-provisionyml) | Create GKE cluster | Once | `cluster`, `network` |
| [gcp-storage.yml](#gcp-storageyml) | Setup GCS buckets for media | Once | `storage`, `permissions` |
| [gcp-backup-storage.yml](#gcp-backup-storageyml) | Setup backup GCS buckets | Once | `backup`, `lifecycle` |
| [mail-server.yml](#mail-serveryml) | Configure email server | Monthly | `postfix`, `ssl` |
| [single-host.yml](#single-hostyml) | Deploy all-in-one server | Varies | `nginx`, `postgresql`, `app` |

## 🎯 Quick Start Commands

### Most Common Operations

```bash
cd infrastructure/ansible

# Deploy application update
ansible-playbook -i inventory/gcp_app.yml \
  --vault-password-file ~/.ansible_vault_pass \
  playbooks/gcp-app-deploy.yml

# Update secrets only (password rotation)
ansible-playbook -i inventory/gcp_app.yml \
  --vault-password-file ~/.ansible_vault_pass \
  playbooks/gcp-app-deploy.yml --tags secrets

# Configure database (after password reset)
ansible-playbook -i inventory/gcp_database.yml \
  --vault-password-file ~/.ansible_vault_pass \
  playbooks/gcp-database.yml --tags postgresql

# Update firewall rules (after adding co-webmaster)
ansible-playbook -i inventory/gcp_database.yml \
  --vault-password-file ~/.ansible_vault_pass \
  playbooks/gcp-database.yml --tags gcp-provision
```

---

## 🔐 Managing Admin SSH Access

**⚠️ CRITICAL**: All admin SSH keys and IP addresses are centralized in `group_vars/all.yml`. This is the **SINGLE SOURCE OF TRUTH** for firewall rules across all infrastructure.

### Adding a New Co-Webmaster

**Step 1: Update centralized admin list**

Edit `group_vars/all.yml`:

```yaml
admin_ssh_keys:
  - user: "pb"
    name: "Piet Barber"
    key: "ssh-ed25519 AAAAC3... pb@host"
    ip: "138.88.187.144/32"

  # Add new entry:
  - user: "newadmin"
    name: "New Admin Name"
    key: "ssh-ed25519 AAAAC3... newadmin@host"  # Get with: cat ~/.ssh/id_ed25519.pub
    ip: "203.0.113.10/32"  # Their public IP + /32 CIDR
```

**Step 2: Update firewall rules on ALL servers**

```bash
cd infrastructure/ansible

# OPTION A: Full playbook run (updates GCP + OS firewalls + user accounts)
# Recommended for adding new admins (creates users, deploys SSH keys, configures both firewall layers)
ansible-playbook -i inventory/gcp_database.yml \
  --vault-password-file ~/.ansible_vault_pass \
  playbooks/gcp-database.yml

ansible-playbook -i inventory/gcp_mail.yml \
  --vault-password-file ~/.ansible_vault_pass \
  playbooks/gcp-mail-server.yml

# OPTION B: GCP firewall only (cloud-level firewall rules)
# Use when updating admin IPs but user accounts already exist
ansible-playbook -i inventory/gcp_database.yml \
  --vault-password-file ~/.ansible_vault_pass \
  playbooks/gcp-database.yml --tags gcp-provision

ansible-playbook -i inventory/gcp_mail.yml \
  --vault-password-file ~/.ansible_vault_pass \
  playbooks/gcp-mail-server.yml --tags gcp-provision
```

**⚠️ Important**: The `--tags firewall` filter does NOT work for GCP firewall updates because GCP firewall tasks are tagged as `gcp-provision`. Always use Option A (full playbook) or Option B (`--tags gcp-provision`) for firewall changes.

**Two-layer firewall architecture:**
- **GCP Cloud Firewall** (outer perimeter): Controls traffic reaching the VM from the internet. Updated via `--tags gcp-provision` or full playbook run.
- **UFW OS Firewall** (host-level): Controls traffic reaching services on the VM. Updated via full playbook run only (no tag filter works correctly).

For complete admin access setup, the full playbook run (Option A) is recommended because it:
1. Updates GCP cloud firewall rules
2. Creates OS user accounts for new admins
3. Deploys SSH keys to authorized_keys
4. Updates UFW OS firewall rules
5. Updates service-level access controls (e.g., PostgreSQL pg_hba.conf)

**Step 3: Verify firewall rule changes**

```bash
# Capture firewall state BEFORE changes
gcloud compute firewall-rules list --format="yaml" --sort-by=name > /tmp/firewall-rules-before.yaml

# Run playbooks (see Step 2 above)

# Capture firewall state AFTER changes
gcloud compute firewall-rules list --format="yaml" --sort-by=name > /tmp/firewall-rules-after.yaml

# Compare to verify expected changes
diff -u /tmp/firewall-rules-before.yaml /tmp/firewall-rules-after.yaml
```

**Step 4: Test SSH access**

```bash
# Test SSH connection
gcloud compute ssh m2s-database --zone=us-east1-b -- "echo 'SSH working!'"
gcloud compute ssh m2s-mail --zone=us-east1-b -- "echo 'SSH working!'"

# Verify OS-level firewall rules on each server
gcloud compute ssh m2s-database --zone=us-east1-b -- "sudo ufw status numbered"  # Database
gcloud compute ssh m2s-mail --zone=us-east1-b -- "sudo ufw status numbered"  # Mail

# Verify firewall rules were updated
gcloud compute firewall-rules describe m2s-database-allow-ssh
gcloud compute firewall-rules describe m2s-mail-allow-ssh
```

### Updating Existing Admin IP

When a co-webmaster's IP address changes:

**Step 1: Update IP in `group_vars/all.yml`**

```yaml
admin_ssh_keys:
  - user: "brian"
    name: "Brian [Last Name]"
    key: "ssh-ed25519 AAAAC3... brian@host"
    ip: "203.0.113.99/32"  # <-- Updated IP
```

**Step 2: Run firewall update** (same commands as above)

### Removing Admin Access

**Step 1: Comment out or remove entry in `group_vars/all.yml`**

```yaml
admin_ssh_keys:
  - user: "pb"
    # ...
  # REMOVED: brian no longer needs access
  # - user: "brian"
  #   name: "Brian [Last Name]"
  #   key: "..."
  #   ip: "..."
```

**Step 2: Run firewall update** (same commands as above)

### Troubleshooting

**"Permission denied (publickey)" when SSHing**

Check:
1. Is the SSH key in `group_vars/all.yml`?
2. Did you run the firewall update playbook?
3. Is the IP address correct? (Check with `curl ifconfig.me`)
4. Are you using the correct SSH key? (`ssh-add -l`)

**Firewall rule shows old IPs**

```bash
# Verify all.yml is correct
cat group_vars/all.yml | grep -A 20 "admin_ssh_keys:"

# Re-run firewall update (GCP layer)
ansible-playbook -i inventory/gcp_database.yml \
  --vault-password-file ~/.ansible_vault_pass \
  playbooks/gcp-database.yml --tags gcp-provision --check  # Dry run first

# Then apply
ansible-playbook -i inventory/gcp_database.yml \
  --vault-password-file ~/.ansible_vault_pass \
  playbooks/gcp-database.yml --tags gcp-provision
```

**"Module format_ssh_key not found"**

This is a custom Jinja2 filter. If it's missing, the simplified approach is to manually format keys:

```yaml
# In gcp_mail/vars.yml
gcp_ssh_public_keys:
  - "{{ admin_ssh_keys[0].user }}:{{ admin_ssh_keys[0].key }}"
  - "{{ admin_ssh_keys[1].user }}:{{ admin_ssh_keys[1].key }}"
  # etc...
```

---

## 🔑 PostgreSQL Password Management

**CRITICAL**: PostgreSQL passwords must stay synchronized between Ansible vault and Kubernetes secrets. Mismatches cause production outages.

### Password Synchronization Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Source of Truth: Kubernetes Secrets (Production)      │
│  - manage2soar-env-ssc (tenant-ssc namespace)          │
│  - manage2soar-env-masa (tenant-masa namespace)        │
└─────────────────────────────────────────────────────────┘
                           ↓
                   Must match exactly
                           ↓
┌─────────────────────────────────────────────────────────┐
│  Ansible Vault: group_vars/localhost/vault.yml         │
│  - vault_postgresql_password_ssc                        │
│  - vault_postgresql_password_masa                       │
└─────────────────────────────────────────────────────────┘
                           ↓
                   Used by playbook
                           ↓
┌─────────────────────────────────────────────────────────┐
│  PostgreSQL Database Server                             │
│  - User: m2s_ssc with password                          │
│  - User: m2s_masa with password                         │
└─────────────────────────────────────────────────────────┘
```

### Safeguard: Password Update Protection

By default, the `gcp-database.yml` playbook will **NOT** update passwords for existing PostgreSQL users. This prevents accidental production outages.

```yaml
# roles/postgresql/defaults/main.yml
postgresql_update_existing_passwords: false  # Default: safe mode
```

When you run the database playbook, existing users will show:
```
⚠️  User m2s_ssc already exists - password NOT updated
To update passwords, set postgresql_update_existing_passwords: true
WARNING: This will break Django apps until K8s secrets are updated!
```

### Intentional Password Rotation (6-Step Procedure)

**Use this procedure when you want to intentionally change PostgreSQL passwords** (e.g., security policy, suspected compromise, periodic rotation):

**Step 1: Generate new passwords**
```bash
cd infrastructure/ansible

# Generate strong passwords (32 characters)
NEW_SSC_PASSWORD="$(openssl rand -base64 32)"
NEW_MASA_PASSWORD="$(openssl rand -base64 32)"

# Save them temporarily (we'll update vault, K8s, and PostgreSQL)
echo "SSC Password: $NEW_SSC_PASSWORD"
echo "MASA Password: $NEW_MASA_PASSWORD"
```

**Step 2: Update Ansible vault with new passwords**
```bash
# Create timestamped backup before modifying vault
cp group_vars/localhost/vault.yml "group_vars/localhost/vault.yml.bak.$(date +%Y%m%d_%H%M%S)"

# Decrypt vault
ansible-vault decrypt group_vars/localhost/vault.yml --vault-password-file ~/.ansible_vault_pass

# Update passwords (escape sed metacharacters)
SSC_ESCAPED="$(printf '%s\n' "$NEW_SSC_PASSWORD" | sed 's/[&/]/\\&/g')"
MASA_ESCAPED="$(printf '%s\n' "$NEW_MASA_PASSWORD" | sed 's/[&/]/\\&/g')"
sed -i "s/vault_postgresql_password_ssc: .*/vault_postgresql_password_ssc: \"${SSC_ESCAPED}\"/" group_vars/localhost/vault.yml
sed -i "s/vault_postgresql_password_masa: .*/vault_postgresql_password_masa: \"${MASA_ESCAPED}\"/" group_vars/localhost/vault.yml

# Re-encrypt vault
ansible-vault encrypt group_vars/localhost/vault.yml --vault-password-file ~/.ansible_vault_pass

# Commit to git
git add group_vars/localhost/vault.yml
git commit -m "security: rotate PostgreSQL passwords"
```

**Step 3: Update Kubernetes secrets with new passwords**
```bash
# Encode passwords to base64 (avoid exposing in command-line arguments visible to ps)
SSC_DB_PASSWORD_B64="$(printf '%s' "$NEW_SSC_PASSWORD" | base64 | tr -d '\n')"
MASA_DB_PASSWORD_B64="$(printf '%s' "$NEW_MASA_PASSWORD" | base64 | tr -d '\n')"

# Update SSC namespace secret via stdin heredoc (preserves existing keys, only changes DB_PASSWORD)
kubectl patch secret manage2soar-env-ssc -n tenant-ssc --type merge --patch "$(cat <<EOF
data:
  DB_PASSWORD: ${SSC_DB_PASSWORD_B64}
EOF
)"

# Update MASA namespace secret via stdin heredoc (preserves existing keys, only changes DB_PASSWORD)
kubectl patch secret manage2soar-env-masa -n tenant-masa --type merge --patch "$(cat <<EOF
data:
  DB_PASSWORD: ${MASA_DB_PASSWORD_B64}
EOF
)"

# Clean up base64 variables
unset SSC_DB_PASSWORD_B64 MASA_DB_PASSWORD_B64

# Verify secrets updated (ensure non-empty decoded passwords)
kubectl get secret -n tenant-ssc manage2soar-env-ssc -o jsonpath='{.data.DB_PASSWORD}' | base64 -d | grep -q . && echo "SSC DB_PASSWORD set"
kubectl get secret -n tenant-masa manage2soar-env-masa -o jsonpath='{.data.DB_PASSWORD}' | base64 -d | grep -q . && echo "MASA DB_PASSWORD set"
```

**Step 4: Restart Django pods to pick up new passwords**
```bash
# Restart SSC deployment
kubectl rollout restart deployment/django-app-ssc -n tenant-ssc
kubectl rollout status deployment/django-app-ssc -n tenant-ssc

# Restart MASA deployment
kubectl rollout restart deployment/django-app-masa -n tenant-masa
kubectl rollout status deployment/django-app-masa -n tenant-masa
```

**Step 5: Update PostgreSQL passwords via playbook**
```bash
# Run playbook with password update flag enabled
ansible-playbook -i inventory/gcp_database.yml \
  --vault-password-file ~/.ansible_vault_pass \
  -e "postgresql_update_existing_passwords=true" \
  playbooks/gcp-database.yml

# Verify playbook success - look for "changed" status on user tasks
```

**Step 6: Verify sites are operational**
```bash
# Test site connectivity
curl -I https://skylinesoaring.org/ | grep "HTTP"  # Should show 200 OK
curl -I https://masa.manage2soar.com/ | grep "HTTP"

# Check pod logs for database connection errors
kubectl logs -n tenant-ssc deployment/django-app-ssc --tail=50 | grep -i "database\|error"
kubectl logs -n tenant-masa deployment/django-app-masa --tail=50 | grep -i "database\|error"

# Clean up temporary password variables
unset NEW_SSC_PASSWORD NEW_MASA_PASSWORD SSC_ESCAPED MASA_ESCAPED
```

**CRITICAL**: Steps 3-5 will cause brief downtime (~30-60 seconds). K8s secrets are updated with NEW passwords, pods restart and attempt to connect, but PostgreSQL still has OLD passwords until Step 5 completes. This creates an authentication failure window. Plan a short maintenance window, or run Steps 3-5 rapidly to minimize the outage.

### Syncing Vault to Match Production (Recommended)

If Ansible vault passwords drift out of sync with production:

```bash
cd infrastructure/ansible

# Extract production passwords from K8s into environment variables (in-memory, avoid /tmp files)
export SSC_DB_PASSWORD="$(kubectl get secret -n tenant-ssc manage2soar-env-ssc -o jsonpath='{.data.DB_PASSWORD}' | base64 -d)"
export MASA_DB_PASSWORD="$(kubectl get secret -n tenant-masa manage2soar-env-masa -o jsonpath='{.data.DB_PASSWORD}' | base64 -d)"

# Decrypt vault
ansible-vault decrypt group_vars/localhost/vault.yml --vault-password-file ~/.ansible_vault_pass

# Update passwords using environment variables (escape sed metacharacters in passwords)
SSC_DB_PASSWORD_ESCAPED="$(printf '%s\n' "$SSC_DB_PASSWORD" | sed 's/[&/]/\\&/g')"
MASA_DB_PASSWORD_ESCAPED="$(printf '%s\n' "$MASA_DB_PASSWORD" | sed 's/[&/]/\\&/g')"
sed -i.bak \
  -e "s/vault_postgresql_password_ssc: .*/vault_postgresql_password_ssc: \"${SSC_DB_PASSWORD_ESCAPED}\"/" \
  -e "s/vault_postgresql_password_masa: .*/vault_postgresql_password_masa: \"${MASA_DB_PASSWORD_ESCAPED}\"/" \
  group_vars/localhost/vault.yml
rm group_vars/localhost/vault.yml.bak

# Re-encrypt vault
ansible-vault encrypt group_vars/localhost/vault.yml --vault-password-file ~/.ansible_vault_pass

# Clean up in-memory secrets (consider also clearing shell history)
unset SSC_DB_PASSWORD MASA_DB_PASSWORD SSC_DB_PASSWORD_ESCAPED MASA_DB_PASSWORD_ESCAPED

# Verify sync (optional - passwords will match but playbook won't update them)
ansible-playbook -i inventory/gcp_database.yml \
  --vault-password-file ~/.ansible_vault_pass \
  playbooks/gcp-database.yml --check
```

### Emergency Recovery: Password Mismatch

⚠️ **WARNING**: This procedure uses manual SSH/SQL commands and violates the IaC-first principle. Use only as a last resort when the production site is down and immediate recovery is required. After using this emergency procedure, you MUST update Ansible vault to match production (see "Syncing Vault to Match Production" above) to restore IaC consistency.

**IaC-First Approach (Recommended)**: Update Ansible vault with K8s password values, then run playbook with `postgresql_update_existing_passwords=true` flag. This ensures infrastructure code matches reality.

If Django apps can't connect to database due to password mismatch and immediate recovery is needed:

```bash
# Fetch passwords from K8s secrets into local shell variables (not files)
SSC_DB_PASSWORD="$(kubectl get secret -n tenant-ssc manage2soar-env-ssc -o jsonpath='{.data.DB_PASSWORD}' | base64 -d)"
MASA_DB_PASSWORD="$(kubectl get secret -n tenant-masa manage2soar-env-masa -o jsonpath='{.data.DB_PASSWORD}' | base64 -d)"

# Apply passwords on the database host via psql variables (psql handles SQL quoting)
# Using :'var' syntax lets psql properly quote the password as a SQL string literal
gcloud compute ssh m2s-database --zone=us-east1-b -- "sudo -u postgres psql -v ssc_pwd='${SSC_DB_PASSWORD}'" <<'EOF'
ALTER USER m2s_ssc WITH PASSWORD :'ssc_pwd';
EOF
gcloud compute ssh m2s-database --zone=us-east1-b -- "sudo -u postgres psql -v masa_pwd='${MASA_DB_PASSWORD}'" <<'EOF'
ALTER USER m2s_masa WITH PASSWORD :'masa_pwd';
EOF

# Clean up in-memory variables
unset SSC_DB_PASSWORD MASA_DB_PASSWORD

# IMPORTANT: Consider clearing your shell history to remove these sensitive commands:
# for i in {1..6}; do history -d -6; done  # Delete last 6 history entries
# Or: history -c && history -r  # Clear all history and reload from file
# CRITICAL: Sync Ansible vault to match production (restore IaC consistency)
# See "Syncing Vault to Match Production" section above
```

---

## gcp-app-deploy.yml

**Purpose**: Deploy Django application to Google Kubernetes Engine  
**Replaces**: `pushy-enhanced-v4.sh` legacy script  
**Location**: `infrastructure/ansible/playbooks/gcp-app-deploy.yml`

### Features

- Multi-tenant support (separate namespaces per club)
- Docker image build and push to GCR
- Kubernetes secrets from Ansible Vault
- Automatic rollback on failure
- Health check verification
- Superuser creation

### Prerequisites

```bash
# Install required collections
ansible-galaxy collection install kubernetes.core
ansible-galaxy collection install google.cloud

# GCP authentication
gcloud auth application-default login
gcloud auth configure-docker

# Vault password file
echo "your_vault_password" > ~/.ansible_vault_pass
chmod 600 ~/.ansible_vault_pass

# Configure variables
cp group_vars/gcp_app.vars.yml.example group_vars/gcp_app/vars.yml
cp group_vars/gcp_app.vault.yml.example group_vars/gcp_app/vault.yml
ansible-vault encrypt group_vars/gcp_app/vault.yml
```

### Usage Patterns

#### Full Deployment (Build + Deploy)

```bash
ansible-playbook -i inventory/gcp_app.yml \
  --vault-password-file ~/.ansible_vault_pass \
  playbooks/gcp-app-deploy.yml
```

**When to use**: Weekly deployments, new features, major updates

**What happens**:
1. Builds Docker image from current codebase
2. Pushes image to Google Container Registry
3. Updates Kubernetes secrets from vault
4. Applies deployment manifests
5. Waits for pods to be ready
6. Runs health checks

#### Deploy Only (Use Existing Image)

```bash
ansible-playbook -i inventory/gcp_app.yml \
  --vault-password-file ~/.ansible_vault_pass \
  playbooks/gcp-app-deploy.yml \
  -e gke_build_image=false -e gke_push_image=false
```

**When to use**: Config-only changes, rollback to previous image

**What happens**: Skips build/push, only updates K8s resources

#### Update Secrets Only

```bash
ansible-playbook -i inventory/gcp_app.yml \
  --vault-password-file ~/.ansible_vault_pass \
  playbooks/gcp-app-deploy.yml --tags secrets
```

**When to use**: Database password rotation, API key updates

**What happens**:
1. Updates Kubernetes secrets from vault
2. Restarts pods to pick up new secrets

#### Deploy Specific Tenant

```bash
ansible-playbook -i inventory/gcp_app.yml \
  --vault-password-file ~/.ansible_vault_pass \
  playbooks/gcp-app-deploy.yml \
  -e gke_deploy_tenant=ssc
```

**When to use**: Single-tenant updates (testing, hotfix one club)

#### Create Superuser After Deployment

```bash
ansible-playbook -i inventory/gcp_app.yml \
  --vault-password-file ~/.ansible_vault_pass \
  playbooks/gcp-app-deploy.yml \
  -e gke_create_superuser=true \
  -e gke_superuser_username=admin \
  -e gke_superuser_email=admin@example.com
```

**When to use**: Initial setup, admin account locked out

### Common Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `gke_build_image` | `true` | Build Docker image |
| `gke_push_image` | `true` | Push to GCR |
| `gke_deploy_tenant` | `all` | Deploy specific tenant or all |
| `gke_image_tag` | `latest` | Docker image tag |
| `gke_create_superuser` | `false` | Create Django superuser |
| `gke_run_migrations` | `true` | Run database migrations |

### Troubleshooting

#### Build Fails

```bash
# Check Docker is running
docker ps

# Check GCR authentication
docker push gcr.io/manage2soar/django-app:test

# Check image exists locally
docker images | grep django-app
```

#### Deployment Fails

```bash
# Check current deployment status
kubectl get pods -n tenant-ssc

# View deployment events
kubectl describe deployment django-app-ssc -n tenant-ssc

# Check for image pull errors
kubectl get events -n tenant-ssc --sort-by='.lastTimestamp'
```

#### Secrets Not Updated

```bash
# Verify vault decryption
ansible-vault view group_vars/gcp_app/vault.yml \
  --vault-password-file ~/.ansible_vault_pass

# Check secret in cluster
kubectl get secret manage2soar-env-ssc -n tenant-ssc -o yaml

# Force secret update
ansible-playbook -i inventory/gcp_app.yml \
  --vault-password-file ~/.ansible_vault_pass \
  playbooks/gcp-app-deploy.yml --tags secrets \
  -e force_update=true
```

---

## gcp-database.yml

**Purpose**: Provision and configure PostgreSQL database server on GCP VM  
**Location**: `infrastructure/ansible/playbooks/gcp-database.yml`

### Features

- GCP VM provisioning (optional)
- PostgreSQL 16 installation and configuration
- Multi-tenant database setup
- SSL/TLS configuration
- Firewall rules
- Automated backups

### Prerequisites

```bash
# Install GCP collection
ansible-galaxy collection install google.cloud

# GCP authentication
gcloud auth application-default login

# Configure inventory
cp inventory/gcp_database.yml.example inventory/gcp_database.yml

# Configure variables
cp group_vars/gcp_database/vars.yml.example group_vars/gcp_database/vars.yml
cp group_vars/gcp_database/vault.yml.example group_vars/gcp_database/vault.yml
ansible-vault encrypt group_vars/gcp_database/vault.yml
```

### Usage Patterns

#### Initial Database Setup (Create VM + Configure)

```bash
ansible-playbook -i inventory/gcp_database.yml \
  --vault-password-file ~/.ansible_vault_pass \
  playbooks/gcp-database.yml
```

**When to use**: First-time setup, new environment

**What happens**:
1. Creates GCP VM instance
2. Installs PostgreSQL 16
3. Configures multi-tenant databases
4. Sets up SSL certificates
5. Configures firewall rules
6. Sets user passwords from vault

#### Configure Existing Database (Skip VM Creation)

```bash
ansible-playbook -i inventory/gcp_database.yml \
  --vault-password-file ~/.ansible_vault_pass \
  playbooks/gcp-database.yml --skip-tags gcp-provision
```

**When to use**: Database reconfiguration, password rotation

**What happens**: Skips VM creation, only configures PostgreSQL

#### PostgreSQL Setup Only

```bash
ansible-playbook -i inventory/gcp_database.yml \
  --vault-password-file ~/.ansible_vault_pass \
  playbooks/gcp-database.yml --tags postgresql
```

**When to use**: PostgreSQL configuration changes, user management

#### SSL Certificate Update

```bash
ansible-playbook -i inventory/gcp_database.yml \
  --vault-password-file ~/.ansible_vault_pass \
  playbooks/gcp-database.yml --tags ssl
```

**When to use**: Certificate expiration, SSL issues

### Password Management (IaC Approach)

**CRITICAL**: Always use Ansible to manage database passwords. Avoid manual `ALTER USER` commands.

#### Update Database Passwords

1. Edit vault:
```bash
cd infrastructure/ansible
ansible-vault edit group_vars/gcp_database/vault.yml \
  --vault-password-file ~/.ansible_vault_pass
```

2. Update password variables:
```yaml
vault_postgresql_password_ssc: "new_secure_password_here"
vault_postgresql_password_masa: "another_secure_password"
```

3. Apply with Ansible:
```bash
ansible-playbook -i inventory/gcp_database.yml \
  --vault-password-file ~/.ansible_vault_pass \
  playbooks/gcp-database.yml --tags postgresql
```

4. Update application secrets:
```bash
# Update K8s secrets with matching passwords
ansible-playbook -i inventory/gcp_app.yml \
  --vault-password-file ~/.ansible_vault_pass \
  playbooks/gcp-app-deploy.yml --tags secrets
```

### Common Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `postgresql_version` | `16` | PostgreSQL major version |
| `postgresql_max_connections` | `200` | Max client connections |
| `postgresql_shared_buffers` | `256MB` | Memory for caching |
| `postgresql_ssl` | `true` | Enable SSL/TLS |
| `database_tenants` | `[ssc, masa]` | Tenant list |

### Troubleshooting

#### Connection Refused

```bash
# Check PostgreSQL is running
gcloud compute ssh m2s-database --zone=us-east1-b \
  --command "systemctl status postgresql"

# Check port is listening
gcloud compute ssh m2s-database --zone=us-east1-b \
  --command "sudo netstat -tlnp | grep 5432"

# Check firewall allows GKE cluster
gcloud compute firewall-rules list --filter="name~'m2s-database'"
```

#### Authentication Failed

**Symptom**: `password authentication failed for user m2s_ssc`

**Solution**:
1. Verify password in vault matches K8s secret
2. Re-run database playbook with `--tags postgresql`
3. Re-run app deploy with `--tags secrets`
4. Restart application pods

```bash
# Check password in vault
ansible-vault view group_vars/gcp_database/vault.yml \
  --vault-password-file ~/.ansible_vault_pass | grep vault_postgresql_password_ssc

# Check password in K8s secret
kubectl get secret manage2soar-env-ssc -n tenant-ssc \
  -o jsonpath='{.data.DB_PASSWORD}' | base64 -d && echo

# Apply IaC fix
ansible-playbook -i inventory/gcp_database.yml \
  --vault-password-file ~/.ansible_vault_pass \
  playbooks/gcp-database.yml --tags postgresql

ansible-playbook -i inventory/gcp_app.yml \
  --vault-password-file ~/.ansible_vault_pass \
  playbooks/gcp-app-deploy.yml --tags secrets
```

---

## gcp-cluster-provision.yml

**Purpose**: Create new GKE cluster with Gateway API support  
**Location**: `infrastructure/ansible/playbooks/gcp-cluster-provision.yml`

### Features

- GKE cluster creation
- Gateway API enablement
- Node pool configuration
- Network policy setup
- Workload identity configuration

### Usage

```bash
ansible-playbook -i inventory/gcp_cluster.yml \
  playbooks/gcp-cluster-provision.yml
```

**When to use**:
- Initial cluster creation
- Creating new environment (staging, DR)
- Cluster rebuild

**What happens**:
1. Creates VPC network
2. Creates GKE cluster
3. Enables Gateway API
4. Configures node pools
5. Sets up workload identity

### Post-Provisioning

After cluster creation, follow [GKE Gateway Ingress Guide](../../infrastructure/ansible/docs/gke-gateway-ingress-guide.md):

```bash
# Get cluster credentials
gcloud container clusters get-credentials m2s-gke-prod \
  --zone=us-east1-b --project=manage2soar

# Verify cluster
kubectl get nodes
kubectl api-resources | grep gateway
```

---

## gcp-storage.yml

**Purpose**: Setup Google Cloud Storage buckets for media files  
**Location**: `infrastructure/ansible/playbooks/gcp-storage.yml`

### Features

- GCS bucket creation
- IAM policy configuration
- Lifecycle rules
- CORS configuration

### Usage

```bash
ansible-playbook -i inventory/gcp_storage.yml \
  playbooks/gcp-storage.yml
```

**When to use**:
- Initial setup
- New tenant buckets
- Bucket policy updates

---

## gcp-backup-storage.yml

**Purpose**: Setup GCS buckets for database backups  
**Location**: `infrastructure/ansible/playbooks/gcp-backup-storage.yml`

### Features

- Backup bucket creation
- Lifecycle policies (retention)
- Cross-region replication
- Access controls

### Usage

```bash
ansible-playbook -i inventory/gcp_backup_storage.yml \
  playbooks/gcp-backup-storage.yml
```

**When to use**:
- Initial backup setup
- Backup retention policy changes
- Disaster recovery preparation

---

## mail-server.yml

**Purpose**: Configure Postfix email server  
**Location**: `infrastructure/ansible/playbooks/mail-server.yml`

### Features

- Postfix installation
- SMTP relay configuration
- DKIM/SPF setup
- TLS configuration

### Usage

```bash
ansible-playbook -i inventory/mail_server.yml \
  --vault-password-file ~/.ansible_vault_pass \
  playbooks/mail-server.yml
```

**When to use**:
- Email server setup
- SMTP configuration changes
- Certificate renewal

---

## single-host.yml

**Purpose**: Deploy complete Manage2Soar instance on single server  
**Location**: `infrastructure/ansible/playbooks/single-host.yml`

### Features

- NGINX reverse proxy
- Gunicorn WSGI server
- PostgreSQL database
- Static file serving
- SSL/TLS with Let's Encrypt

### Usage

```bash
ansible-playbook -i inventory/single_host.yml \
  --vault-password-file ~/.ansible_vault_pass \
  playbooks/single-host.yml
```

**When to use**:
- Small club deployments (<200 members)
- Development/testing environments
- Cost-optimized hosting

**See**: [Infrastructure README](../../infrastructure/ansible/README.md#single-host-deployment) for complete guide

---

## 🔐 Vault Management

### View Vault Contents

```bash
ansible-vault view group_vars/gcp_app/vault.yml \
  --vault-password-file ~/.ansible_vault_pass
```

### Edit Vault

```bash
ansible-vault edit group_vars/gcp_app/vault.yml \
  --vault-password-file ~/.ansible_vault_pass
```

### Encrypt New File

```bash
ansible-vault encrypt group_vars/new_group/vault.yml \
  --vault-password-file ~/.ansible_vault_pass
```

### Decrypt for Debugging (Temporary)

```bash
ansible-vault decrypt group_vars/gcp_app/vault.yml \
  --vault-password-file ~/.ansible_vault_pass
# Make changes...
ansible-vault encrypt group_vars/gcp_app/vault.yml \
  --vault-password-file ~/.ansible_vault_pass
```

---

## 🧪 Testing Playbooks

### Syntax Check

```bash
ansible-playbook playbooks/gcp-app-deploy.yml --syntax-check
```

### Dry Run (Check Mode)

```bash
ansible-playbook -i inventory/gcp_app.yml \
  --vault-password-file ~/.ansible_vault_pass \
  playbooks/gcp-app-deploy.yml \
  --check
```

### List Tasks

```bash
ansible-playbook playbooks/gcp-app-deploy.yml --list-tasks
```

### List Tags

```bash
ansible-playbook playbooks/gcp-app-deploy.yml --list-tags
```

---

## 📚 References

- [Ansible README](../../infrastructure/ansible/README.md)
- [GKE Deployment Guide](../../infrastructure/ansible/docs/gke-deployment-guide.md)
- [GKE Post-Deployment](../../infrastructure/ansible/docs/gke-post-deployment.md)
- [Ansible Best Practices](https://docs.ansible.com/ansible/latest/user_guide/playbooks_best_practices.html)

---

**Last Updated**: January 17, 2026  
**Maintained By**: Infrastructure Team
