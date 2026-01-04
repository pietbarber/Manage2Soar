# GKE Post-Deployment Steps

This guide covers essential steps after deploying Django apps to GKE, including database setup, migrations, and superuser creation.

## Prerequisites

- GKE cluster deployed with Django pods running
- PostgreSQL database provisioned and accessible
- Vault passwords configured for database access
- kubectl configured with cluster access

## Quick Start Checklist

- [ ] Verify database connectivity from pods
- [ ] Create GCS bucket for media storage
- [ ] Run database migrations
- [ ] Create Django superuser(s)
- [ ] Verify application access

## Step 1: Verify Database Connectivity

### Check Database Configuration

Verify pods can reach the database with correct credentials:

```bash
# Check database host in secrets
kubectl get secret manage2soar-env-ssc -n tenant-ssc -o jsonpath='{.data.DB_HOST}' | base64 -d && echo

# Should show internal database IP (e.g., 10.142.0.2)
# If wrong, see troubleshooting section below
```

### Test Database Connection

```bash
# Test connection from pod
kubectl exec -n tenant-ssc deployment/django-app-ssc -- python manage.py check --database default

# Expected output: "System check identified no issues (0 silenced)."
```

## Step 2: Verify/Set Database Passwords

The PostgreSQL users should have passwords set during initial database provisioning. If passwords weren't set correctly, use Ansible to set them.

### Verify Passwords in Vault

```bash
cd infrastructure/ansible

# Verify passwords are in vault
ansible-vault view group_vars/gcp_database/vault.yml --vault-password-file ~/.ansible_vault_pass | grep vault_postgresql_password
```

### Set Passwords Using Ansible (IaC Approach - Recommended)

Create a temporary playbook that references vault variables to avoid exposing passwords in command history:

```bash
cd infrastructure/ansible

# Create a one-time password reset playbook in the ansible directory
cat > set-db-passwords.yml << 'EOF'
---
- hosts: all
  become: true
  become_user: postgres  # Requires 'postgres' system user with DB admin privileges
  vars_files:
    - group_vars/gcp_database/vault.yml
  vars:
    # PostgreSQL connection parameters - uses local socket by default
    # Change to 127.0.0.1 if socket auth is not configured
    db_host: ""
    db_port: 5432
  tasks:
    - name: Set m2s_ssc password
      community.postgresql.postgresql_user:
        name: m2s_ssc
        password: "{{ vault_postgresql_password_ssc }}"
        state: present
        login_host: "{{ db_host | default(omit, true) }}"
        login_port: "{{ db_port }}"
    - name: Set m2s_masa password
      community.postgresql.postgresql_user:
        name: m2s_masa
        password: "{{ vault_postgresql_password_masa }}"
        state: present
        login_host: "{{ db_host | default(omit, true) }}"
        login_port: "{{ db_port }}"
EOF

# Run the playbook (must be run from infrastructure/ansible directory)
ansible-playbook -i "YOUR_DB_IP," \
  --user=$(whoami) \
  --ssh-extra-args="-i ~/.ssh/google_compute_engine" \
  --vault-password-file ~/.ansible_vault_pass \
  set-db-passwords.yml

# Remove temporary playbook
rm set-db-passwords.yml
```

**Note**: Replace `YOUR_DB_IP` with your database server's external IP.

> **For Managed Database Services (e.g., Cloud SQL)**: The playbook above requires SSH access
> to the database server, which isn't available with managed services. For Cloud SQL:
> - Use Cloud SQL Admin API or `gcloud sql users set-password` command
> - Or connect via Cloud SQL Proxy from a bastion host with psql
> - Passwords should still be stored in Ansible Vault for consistency

## Step 3: Create GCS Bucket for Media Storage

Django uses Google Cloud Storage for media files (profile photos, avatars, etc.):

```bash
# Create bucket (replace region if needed)
gcloud storage buckets create gs://manage2soar \
  --project=manage2soar \
  --location=us-east1 \
  --uniform-bucket-level-access

# Verify bucket exists
gcloud storage buckets list --project=manage2soar | grep manage2soar
```

**Why this is needed**: User profile creation (including superuser) generates avatars that are stored in GCS.

## Step 4: Run Database Migrations

Run migrations to create all Django database tables:

```bash
# SSC tenant
kubectl exec -n tenant-ssc deployment/django-app-ssc -- python manage.py migrate

# MASA tenant
kubectl exec -n tenant-masa deployment/django-app-masa -- python manage.py migrate

# Expected: All migrations applied successfully (122+ migrations)
```

**Important**: Migrations must be run before creating superuser accounts.

## Step 5: Create Django Superuser

### Option A: Using Ansible Playbook (IaC - Recommended)

1. Add superuser password to vault:
```bash
cd infrastructure/ansible
ansible-vault edit group_vars/gcp_app/vault.yml --vault-password-file ~/.ansible_vault_pass
```

Add this line:
```yaml
vault_django_superuser_password: "your_secure_password_here"
```

2. Enable superuser creation in inventory (already configured in `inventory/gcp_app.yml`):
```yaml
gke_create_superuser: true
django_superuser_username: "admin"
django_superuser_email: "admin@manage2soar.com"
```

3. Run deployment to create superuser:
```bash
ansible-playbook -i inventory/gcp_app.yml \
  --vault-password-file ~/.ansible_vault_pass \
  playbooks/gcp-app-deploy.yml \
  --tags superuser \
  -e gke_image_tag=<YOUR_CURRENT_IMAGE_TAG>
```

### Option B: Interactive Creation (for testing only)

> ⚠️ **SECURITY WARNING**: Avoid passing passwords in command-line arguments or environment
> variables, as they can appear in shell history, process listings, and system logs.
> **Use Option A (Ansible) for production deployments.**
> If you must use this approach:
> - Run `createsuperuser` interactively inside the pod
> - Use a strong password and rotate it via Django admin as soon as possible

```bash
# SSC tenant (testing only - interactive prompt for password)
kubectl exec -it -n tenant-ssc deployment/django-app-ssc -- \
  python manage.py createsuperuser

# MASA tenant (testing only - interactive prompt for password)
kubectl exec -it -n tenant-masa deployment/django-app-masa -- \
  python manage.py createsuperuser
```

## Step 6: Verify Application Access

```bash
# Check pod status
kubectl get pods -n tenant-ssc
kubectl get pods -n tenant-masa

# Get Gateway IP
kubectl get gateway manage2soar-gateway -n default -o jsonpath='{.status.addresses[0].value}' && echo

# Test access (replace with your domain or use /etc/hosts)
# If using /etc/hosts, add a line like: <GATEWAY_IP> ssc.manage2soar.com
curl -H "Host: ssc.manage2soar.com" http://GATEWAY_IP/
```

## Troubleshooting

### Issue: Wrong Database IP in Secrets

**Symptom**: Connection timeout to 10.128.0.2 instead of correct database IP

**Cause**: Ansible variable precedence - `gke_db_host` defaults evaluate before inventory vars

**Fix (IaC Approach - Recommended)**:
```bash
# 1. Update inventory to use postgresql_host (not gke_db_host)
# Edit inventory/gcp_app.yml:
#   postgresql_host: "YOUR_CORRECT_IP"

# 2. Re-run deployment to regenerate secrets with correct IP
cd infrastructure/ansible
ansible-playbook -i inventory/gcp_app.yml \
  --vault-password-file ~/.ansible_vault_pass \
  playbooks/gcp-app-deploy.yml \
  --tags secrets

# 3. Restart pods to pick up new secret
kubectl delete pods -n tenant-ssc --all
```

**Emergency Fix (manual - only when IaC isn't immediately possible)**:
```bash
# IMPORTANT: Generate YOUR OWN base64 value - do not copy the placeholder below!
# To create base64 value for your IP address:
#   echo -n "YOUR_CORRECT_IP" | base64  # e.g., echo -n "10.142.0.2" | base64

# First, inspect current DB_HOST value in the secret
kubectl get secret manage2soar-env-ssc -n tenant-ssc -o jsonpath='{.data.DB_HOST}' | base64 -d; echo

# Patch only the DB_HOST field (replace placeholder with YOUR base64-encoded IP)
kubectl patch secret manage2soar-env-ssc -n tenant-ssc \
  --type='json' \
  -p='[{"op":"replace","path":"/data/DB_HOST","value":"<YOUR_BASE64_ENCODED_IP>"}]'

kubectl delete pods -n tenant-ssc --all

# NOTE: Document this manual fix and update IaC to prevent recurrence!
```

### Issue: Password Authentication Failed

**Symptom**: `FATAL: password authentication failed for user "m2s_ssc"`

**Cause**: PostgreSQL user password not set during initial database provisioning

**Fix**: See Step 2 above - use Ansible to set passwords

### Issue: pg_hba.conf Rejects Connection (no encryption)

**Symptom**: `pg_hba.conf rejects connection... no encryption`

**Cause**: Django not using SSL mode for PostgreSQL connections

**Fix**: Ensure `DB_SSLMODE=require` in secrets and Django settings.py has:
```python
DATABASES = {
    "default": {
        ...
        "OPTIONS": {
            "sslmode": os.getenv("DB_SSLMODE", "require"),
        },
    },
}
```

### Issue: Relation Does Not Exist

**Symptom**: `django.db.utils.ProgrammingError: relation "members_member" does not exist`

**Cause**: Migrations not run - database tables don't exist

**Fix**: Run migrations (see Step 4)

### Issue: GCS Bucket Does Not Exist

**Symptom**: `404 POST https://storage.googleapis.com/... The specified bucket does not exist`

**Cause**: Media storage bucket not created

**Fix**: Create GCS bucket (see Step 3)

### Issue: Deployment Rollout Timeout

**Symptom**: Deployment times out waiting for Gateway health checks

**Cause**: Gateway NEG (Network Endpoint Group) health checks can take 5-10 minutes

**Solutions**:
1. Wait longer - health checks will eventually pass
2. Manually delete old pods to force traffic to new pods:
   ```bash
   kubectl delete pod OLD_POD_NAME -n tenant-ssc
   ```
3. Increase `progressDeadlineSeconds` in deployment (default: 600s)

### Issue: Pods Have Old Secrets After Update

**Symptom**: Pods running but using old environment variables

**Cause**: Secrets updated but pods not restarted

**Fix**:
```bash
# Restart all pods to pick up new secrets
kubectl delete pods -n tenant-ssc --all
kubectl delete pods -n tenant-masa --all
```

## Post-Deployment Tasks

Once superuser is created:

1. **Configure Site Settings**:
   - Log in to Django admin: `http://ssc.manage2soar.com/admin/`
   - Navigate to Site Configuration
   - Set club name, contact info, operational settings

2. **Create Initial Data**:
   - Add airfield(s)
   - Add gliders and towplanes
   - Configure duty roles
   - Set up membership status options

3. **Set Up DNS**:
   - Point `ssc.manage2soar.com` to Gateway IP
   - Point `masa.manage2soar.com` to Gateway IP
   - Wait for SSL certificate provisioning (automatic)

4. **Test Multi-Tenant Isolation**:
   - Verify SSC and MASA have separate databases
   - Confirm data isolation between tenants

## References

- [Gateway API Deployment Guide](gke-gateway-ingress-guide.md)
- [Database Provisioning](../playbooks/gcp-database.yml)
- [Superuser IaC Implementation](../roles/gke-deploy/tasks/superuser.yml)
