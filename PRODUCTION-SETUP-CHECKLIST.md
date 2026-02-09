# Production Deployment Readiness Checklist

Use this checklist to track your laptop setup progress for production deployments.

## ✅ Phase 1: Install Tools - COMPLETE

- [x] Google Cloud CLI (`gcloud`) - v503.0.0
- [x] kubectl - v1.32.0  
- [x] Docker Engine - v27.4.1
- [x] Ansible + collections - v2.18.1 with kubernetes.core, google.cloud, community.postgresql
- [x] Optional: k9s (v0.50.18), helm (v3.14.0), jq (v1.7.1)
- [x] Log out and log back in (for docker group membership)

**Installation completed via:**
```bash
# Ubuntu/Debian:
./infrastructure/scripts/setup-admin-ubuntu.sh

# macOS with Homebrew:
./infrastructure/scripts/setup-admin-homebrew.sh
```

## ✅ Phase 2: Authenticate & Configure - COMPLETE

- [x] Authenticate with GCP  
  - Account: pb@pietbarber.com
  - Project: manage2soar
  - Already configured via `gcloud init`

- [x] Configure Docker for GCR
  ```bash
  gcloud auth configure-docker gcr.io  # DONE
  ```

- [x] Get kubectl access to GKE cluster
  ```bash
  gcloud container clusters get-credentials manage2soar-cluster --zone=us-east1-b --project=manage2soar  # DONE
  ```

- [x] Verify kubectl access
  - Cluster: manage2soar-cluster (3 nodes, v1.33.5)
  - Namespaces: tenant-ssc, tenant-masa (both running 2 pods)
  - Current deployed version: `gcr.io/manage2soar/manage2soar:20260208-0126-00b1c36`

**Note:** Docker group requires `newgrp docker` in each new terminal, or log out/back in for permanent access.

## ⚠️ Phase 3: Choose Deployment Method

**You have two options:**

### Option A: Quick Deploy (Recommended for now)
Use `quick-deploy.sh` - builds Docker image, pushes to GCR, updates Kubernetes deployments.

**Prerequisites:**
- ✅ kubectl access (done)
- ✅ Docker GCR auth (done)  
- ⚠️ Must run `newgrp docker` in each terminal (or log out/back in once)

**Usage:**
```bash
# Activate docker group
newgrp docker

# Deploy current code
./quick-deploy.sh

# It will:
# 1. Build: docker build -t gcr.io/manage2soar/manage2soar:TIMESTAMP-HASH .
# 2. Push: docker push gcr.io/manage2soar/manage2soar:TIMESTAMP-HASH
# 3. Update both tenants: kubectl set image deployment/django-app-ssc ...
# 4. Wait for rollout: kubectl rollout status ...
```

### Option B: Full Ansible Setup (For complete infrastructure management) - ✅ COMPLETE
Required for: secrets management, database provisioning, cluster provisioning, multi-tenant config.

- [x] Vault password file configured: `~/.ansible_vault_file` ✓
- [x] Extracted Ansible configuration from backup tarball ✓
- [x] Generated SSH key: `~/.ssh/id_ed25519` ✓
- [x] Added SSH key to GCP project metadata ✓
- [x] Verified SSH connectivity to all hosts ✓
- [x] Verified Ansible ping to all hosts ✓
- [x] Verified Ansible vault access ✓

**Configured Hosts:**
- **m2s-database** (34.74.153.95): PostgreSQL 17.7 on Ubuntu 24.04 ✓
- **m2s-mail** (35.237.42.68): Postfix mail server ✓

**Test connectivity:**
```bash
cd infrastructure/ansible
./test-connectivity.sh
```

**Available playbooks:**
```bash
# Database server management
ansible-playbook -i inventory/gcp_database.yml \
  --vault-password-file ~/.ansible_vault_file \
  playbooks/gcp-database.yml

# Mail server management  
ansible-playbook -i inventory/gcp_mail.yml \
  --vault-password-file ~/.ansible_vault_file \
  playbooks/gcp-mail-server.yml

# GKE app deployment (complete Django deployment with secrets)
ansible-playbook -i inventory/gcp_app.yml \
  --vault-password-file ~/.ansible_vault_file \
  playbooks/gcp-app-deploy.yml
```

## ✅ Phase 4: Verify Setup - COMPLETE

- [x] Test GCP connection
  ```bash
  gcloud projects list  # ✓ manage2soar project active
  gcloud container clusters list  # ✓ manage2soar-cluster running
  ```

- [x] Test kubectl
  ```bash
  kubectl cluster-info  # ✓ Connected to https://34.75.132.111
  kubectl get pods --all-namespaces  # ✓ Both tenants running 2 pods each
  ```

- [x] Test Docker
  ```bash
  docker run hello-world  # ✓ Works (requires newgrp docker)
  docker images  # ✓ Can pull from gcr.io/manage2soar
  ```
  **Note:** Docker requires `newgrp docker` in each new terminal, or log out/back in once

- [x] Test Ansible
  ```bash
  ansible --version  # ✓ v2.16.3
  ansible-galaxy collection list | grep -E "kubernetes|google.cloud|community.postgresql"  # ✓ All present
  ```

## 🚀 Phase 5: Ready to Deploy!

Your laptop is now production-ready! Choose your deployment method:

### Quick Deploy (Immediate code deployments)
```bash
# Make script executable (first time only)
chmod +x quick-deploy.sh

# Activate docker group
newgrp docker

# Deploy current HEAD
./quick-deploy.sh
```

**Current Status:**
- Production version: `20260208-0126-00b1c36` (PR #617)
- Your HEAD: `2352820` (PR #619 - Roll Again removed dates)
- Ready to deploy: YES ✓

### Full Ansible Deploy (Complete infrastructure management)

First, complete Phase 3 Option B (set up Ansible configs), then:

```bash
cd infrastructure/ansible

# Test deployment (dry run)
ansible-playbook -i inventory/gcp_app.yml \
  --vault-password-file ~/.ansible_vault_pass \
  playbooks/gcp-app-deploy.yml \
  --check --diff

# Deploy for real
ansible-playbook -i inventory/gcp_app.yml \
  --vault-password-file ~/.ansible_vault_pass \
  playbooks/gcp-app-deploy.yml
```

- [ ] Verify deployment
  ```bash
  kubectl get pods -n <YOUR_NAMESPACE>
  kubectl logs -f deployment/django-app -n <YOUR_NAMESPACE>
  ```

- [ ] Test application
  ```bash
  # Port forward for testing
  kubectl port-forward deployment/django-app 8000:8000 -n <YOUR_NAMESPACE>
  # Visit http://localhost:8000
  ```

## 🚨 Troubleshooting

If something goes wrong, check:

- [ ] gcloud authentication: `gcloud auth list`
- [ ] kubectl context: `kubectl config current-context`
- [ ] Docker daemon running: `docker ps`
- [ ] Ansible vault password: `cat ~/.ansible_vault_pass`
- [ ] GKE cluster exists: `gcloud container clusters list`
- [ ] Pod logs: `kubectl logs -f deployment/django-app -n <NAMESPACE>`
- [ ] Pod events: `kubectl describe pod <POD_NAME> -n <NAMESPACE>`

## 📚 Documentation

- Full setup guide: [docs/admin-workstation-setup.md](docs/admin-workstation-setup.md)
- Infrastructure overview: [infrastructure/README.md](infrastructure/README.md)
- GCP database deployment: [infrastructure/docs/gcp-database-deployment.md](infrastructure/docs/gcp-database-deployment.md)

## 🔐 Security Reminders

- [ ] Never commit to git:
  - `~/.ansible_vault_pass`
  - `infrastructure/ansible/inventory/gcp_app.yml`
  - `infrastructure/ansible/group_vars/gcp_app/vars.yml`
  - `infrastructure/ansible/group_vars/gcp_app/vault.yml` (unless encrypted)
  - Any `*.json` service account keys

- [ ] File permissions set correctly:
  ```bash
  chmod 600 ~/.ansible_vault_pass
  chmod 600 infrastructure/ansible/inventory/*.yml
  ```

## ✨ You're Ready!

Once all checkboxes are ticked, you're ready to deploy to production! 🚀
