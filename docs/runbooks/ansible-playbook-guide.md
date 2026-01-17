# Ansible Playbook Guide

Complete reference for all Ansible playbooks used in Manage2Soar infrastructure management.

## 📖 Overview

This guide documents all Ansible playbooks in `infrastructure/ansible/playbooks/`, their purpose, usage patterns, and common scenarios. Always refer to this guide before manual operations - IaC-first approach.

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
