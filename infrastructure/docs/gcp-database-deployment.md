# GCP Database Server Deployment

This document describes how to deploy a dedicated PostgreSQL database server on Google Cloud Platform (GCP) using Ansible automation.

## Overview

The GCP database deployment supports:

- **Automated VM provisioning**: Creates GCP VM if it doesn't exist
- **Idempotent operation**: Safe to run multiple times
- **Multi-tenant databases**: One database per club/tenant
- **SSL/TLS encryption**: Secure connections to PostgreSQL
- **Firewall rules**: GCP and UFW firewall configuration
- **Automated backups**: Daily PostgreSQL backups with retention

## Architecture

```mermaid
flowchart TB
    subgraph GCP["Google Cloud Platform"]
        subgraph VPC["VPC Network"]
            subgraph DatabaseVM["Database VM (m2s-database)"]
                PG["PostgreSQL 17"]
                UFW["UFW Firewall"]
                SSL["SSL/TLS Certs"]
            end
            FW["GCP Firewall Rules<br/>• allow-postgresql (5432)<br/>• allow-ssh (22)"]
        end
    end

    subgraph K8s["Kubernetes Cluster"]
        Pod1["M2S Pod (SSC)"]
        Pod2["M2S Pod (MASA)"]
    end

    subgraph Admin["Admin Workstation"]
        Ansible["Ansible Controller"]
        GCloud["gcloud CLI"]
    end

    Ansible -->|"1. Provision VM"| GCP
    Ansible -->|"2. Configure PostgreSQL"| DatabaseVM
    Pod1 -->|"SSL :5432"| PG
    Pod2 -->|"SSL :5432"| PG
    FW -.->|"controls"| DatabaseVM
```

## Prerequisites

### 1. Install Required Tools

```bash
# Ansible and GCP collection
pip install ansible
ansible-galaxy collection install google.cloud community.postgresql community.general

# GCP CLI
curl https://sdk.cloud.google.com | bash
gcloud init
```

### 2. GCP Authentication

Choose one method:

**Option A: Application Default Credentials (Recommended)**
```bash
gcloud auth application-default login
```

**Option B: Service Account Key**
```bash
# Create service account in GCP Console
# Download JSON key file
# Set in group_vars:
gcp_auth_kind: "serviceaccount"
gcp_service_account_file: "/path/to/key.json"
```

### 3. Required GCP Permissions

The authenticated user/service account needs:
- `roles/compute.admin` - Create/manage VMs
- `roles/compute.networkAdmin` - Create firewall rules

## Quick Start

### Step 1: Copy Configuration Files

```bash
cd infrastructure/ansible

# Inventory
cp inventory/gcp_database.yml.example inventory/gcp_database.yml

# Variables
mkdir -p group_vars/gcp_database
cp group_vars/gcp_database.vars.yml.example group_vars/gcp_database/vars.yml
```

### Step 2: Initialize Secrets

Use the automated script:
```bash
../scripts/initialize-vault-secrets.sh group_vars/gcp_database/vault.yml
```

Or manually create the vault:
```bash
# Create vault password file
echo "your-secure-password" > ~/.ansible_vault_pass
chmod 600 ~/.ansible_vault_pass

# Create encrypted vault
ansible-vault create group_vars/gcp_database/vault.yml \
  --vault-password-file ~/.ansible_vault_pass
```

### Step 3: Edit Configuration

```bash
# Edit inventory (add your settings)
vim inventory/gcp_database.yml

# Edit variables (project, machine type, tenants)
vim group_vars/gcp_database/vars.yml

# Edit secrets (passwords)
ansible-vault edit group_vars/gcp_database/vault.yml \
  --vault-password-file ~/.ansible_vault_pass
```

### Step 4: Run the Playbook

```bash
# Full deployment (provision VM + configure PostgreSQL)
ansible-playbook -i inventory/gcp_database.yml \
  --vault-password-file ~/.ansible_vault_pass \
  playbooks/gcp-database.yml

# Configuration only (VM already exists)
ansible-playbook -i inventory/gcp_database.yml \
  --vault-password-file ~/.ansible_vault_pass \
  playbooks/gcp-database.yml --skip-tags gcp-provision
```

## Configuration Reference

### VM Provisioning Options

| Variable | Default | Description |
|----------|---------|-------------|
| `gcp_project` | (required) | GCP project ID |
| `gcp_vm_provision` | `true` | Create VM if doesn't exist |
| `gcp_vm_name` | `m2s-database` | VM instance name |
| `gcp_machine_type` | `e2-small` | GCP machine type |
| `gcp_zone` | `us-east1-b` | GCP zone |
| `gcp_boot_disk_size_gb` | `20` | Boot disk size |

### PostgreSQL Options

| Variable | Default | Description |
|----------|---------|-------------|
| `postgresql_version` | `17` | PostgreSQL version |
| `postgresql_multi_tenant` | `false` | Enable multi-tenant mode |
| `postgresql_ssl_enabled` | `false` | Enable SSL connections |
| `postgresql_ssl_require_remote` | `true` | Require SSL for remote |
| `postgresql_remote_access_cidrs` | `[]` | CIDRs allowed to connect |

### Multi-Tenant Configuration

```yaml
postgresql_multi_tenant: true
postgresql_tenants:
  - prefix: "ssc"
    name: "Skyline Soaring Club"
    password: "{{ vault_postgresql_password_ssc }}"
  - prefix: "masa"
    name: "Mid-Atlantic Soaring Association"
    password: "{{ vault_postgresql_password_masa }}"
```

Each tenant gets:
- Database: `m2s_{prefix}` (e.g., `m2s_ssc`)
- User: `m2s_{prefix}` (e.g., `m2s_ssc`)
- Isolated access (can only access own database)

## Deployment Workflow

```mermaid
flowchart LR
    subgraph Phase1["Phase 1: GCP Provisioning"]
        A1[Check VM Exists] --> A2{Exists?}
        A2 -->|No| A3[Create VM]
        A2 -->|Yes| A4[Use Existing]
        A3 --> A5[Create Firewall Rules]
        A4 --> A5
        A5 --> A6[Wait for SSH]
    end

    subgraph Phase2["Phase 2: Configuration"]
        B1[Update APT] --> B2[Install Packages]
        B2 --> B3[Configure UFW]
        B3 --> B4[Setup SSL]
        B4 --> B5[Configure PostgreSQL]
        B5 --> B6[Create Databases]
        B6 --> B7[Configure Backups]
    end

    Phase1 --> Phase2
```

## Security Considerations

### Network Security

1. **GCP Firewall**: Only allows PostgreSQL from specified CIDRs
2. **UFW Firewall**: Additional host-level protection
3. **SSL/TLS**: Required for remote connections in production
4. **pg_hba.conf**: Strict authentication rules

### Access Control

```mermaid
flowchart TB
    subgraph Allowed["Allowed Connections"]
        K8s["K8s Pods<br/>(10.0.0.0/8)"]
        Admin["Admin via SSH<br/>(restricted IPs)"]
    end

    subgraph Denied["Denied"]
        Internet["Public Internet"]
        Other["Other GCP Projects"]
    end

    subgraph Database["Database Server"]
        PG["PostgreSQL :5432"]
    end

    K8s -->|"SSL + password"| PG
    Admin -->|"SSH + sudo"| Database
    Internet -.->|"❌ blocked"| Database
    Other -.->|"❌ blocked"| Database
```

### Secrets Management

- **Vault encryption**: All passwords stored in ansible-vault
- **No secrets in git**: All secret files are gitignored
- **Unique passwords**: Each tenant has separate credentials
- **Generated secrets**: Use provided scripts for secure random values

## Connecting from Applications

### Django Configuration

```python
# settings.py
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'm2s_ssc',  # or m2s_masa, etc.
        'USER': 'm2s_ssc',
        'PASSWORD': os.environ['DATABASE_PASSWORD'],
        'HOST': 'your-database-ip',
        'PORT': '5432',
        'OPTIONS': {
            'sslmode': 'require',  # if SSL enabled
        },
    }
}
```

### Connection String

```
postgresql://m2s_ssc:PASSWORD@35.123.45.67:5432/m2s_ssc?sslmode=require
```

## Maintenance

### View Vault Secrets

```bash
ansible-vault view group_vars/gcp_database/vault.yml \
  --vault-password-file ~/.ansible_vault_pass
```

### Add a New Tenant

1. Add tenant to `vars.yml`:
   ```yaml
   postgresql_tenants:
     - prefix: "newclub"
       name: "New Soaring Club"
       password: "{{ vault_postgresql_password_newclub }}"
   ```

2. Add password to vault:
   ```bash
   ansible-vault edit group_vars/gcp_database/vault.yml
   # Add: vault_postgresql_password_newclub: "generated-password"
   ```

3. Run playbook:
   ```bash
   ansible-playbook -i inventory/gcp_database.yml \
     --vault-password-file ~/.ansible_vault_pass \
     playbooks/gcp-database.yml --tags postgresql
   ```

### Backup and Restore

Backups are stored on the database server:
```bash
# SSH to database server
ssh your-db-server

# List backups
ls -la /var/backups/postgresql/

# Manual backup
sudo -u postgres pg_dump m2s_ssc > backup.sql

# Restore
sudo -u postgres psql m2s_ssc < backup.sql
```

## Troubleshooting

### Cannot Connect to PostgreSQL

1. Check GCP firewall rules in Console
2. Verify `postgresql_remote_access_cidrs` includes your IP
3. Check UFW status: `sudo ufw status`
4. Check PostgreSQL logs: `sudo tail -f /var/log/postgresql/postgresql-17-main.log`

### VM Provisioning Fails

1. Verify GCP authentication: `gcloud auth list`
2. Check project permissions
3. Verify quota availability in the zone
4. Check for existing VM with same name

### SSL Certificate Issues

1. Verify certificate exists: `ls -la /etc/postgresql/17/main/server.*`
2. Check certificate permissions (must be owned by postgres)
3. For custom certs, set `postgresql_ssl_generate_self_signed: false`

## Related Documentation

- [Single-Host Deployment](single-host-architecture.md)
- [Ansible README](../ansible/README.md)
- [PostgreSQL Role](../ansible/roles/postgresql/README.md)
