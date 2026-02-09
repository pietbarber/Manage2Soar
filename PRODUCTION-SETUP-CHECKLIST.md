# Production Deployment Readiness Checklist

Use this checklist to track your laptop setup progress for production deployments.

## ✅ Phase 1: Install Tools - COMPLETE

- [x] Google Cloud CLI (`gcloud`)
- [x] kubectl
- [x] Docker Engine
- [x] Ansible + required collections (kubernetes.core, google.cloud, community.postgresql)
- [x] Optional: k9s, helm, jq
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
  - Account: *(your GCP account)*
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
  - Cluster: manage2soar-cluster (check with `gcloud container clusters list`)
  - Namespaces: tenant-ssc, tenant-masa
  - Current deployed version: check with `kubectl get deployment -n tenant-ssc -o jsonpath='{.items[0].spec.template.spec.containers[0].image}'`

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

- [x] Vault password file configured: `~/.ansible_vault_pass` ✓
- [x] Extracted Ansible configuration from backup tarball ✓
- [x] Generated SSH key: `~/.ssh/id_ed25519` ✓
- [x] Added SSH key to GCP project metadata ✓
- [x] Verified SSH connectivity to all hosts ✓
- [x] Verified Ansible ping to all hosts ✓
- [x] Verified Ansible vault access ✓

**Configured Hosts:**
- **m2s-database**: PostgreSQL server (get IP via `gcloud compute instances describe m2s-database --zone=us-east1-b --format='get(networkInterfaces[0].accessConfigs[0].natIP)'`)
- **m2s-mail**: Postfix mail server (get IP via `gcloud compute instances describe m2s-mail --zone=us-east1-b --format='get(networkInterfaces[0].accessConfigs[0].natIP)'`)

**Test connectivity:**
```bash
cd infrastructure/ansible
./test-connectivity.sh
```

**Available playbooks:**
```bash
# Database server management
ansible-playbook -i inventory/gcp_database.yml \
  --vault-password-file ~/.ansible_vault_pass \
  playbooks/gcp-database.yml

# Mail server management  
ansible-playbook -i inventory/gcp_mail.yml \
  --vault-password-file ~/.ansible_vault_pass \
  playbooks/gcp-mail-server.yml

# GKE app deployment (complete Django deployment with secrets)
ansible-playbook -i inventory/gcp_app.yml \
  --vault-password-file ~/.ansible_vault_pass \
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
  kubectl cluster-info  # ✓ Shows cluster master endpoint for current context
  kubectl get pods --all-namespaces  # ✓ Both tenants running pods
  ```

- [x] Test Docker
  ```bash
  docker run hello-world  # ✓ Works (requires newgrp docker)
  docker images  # ✓ Can pull from gcr.io/manage2soar
  ```
  **Note:** Docker requires `newgrp docker` in each new terminal, or log out/back in once

- [x] Test Ansible
  ```bash
  ansible --version  # ✓ Check version is installed
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

**Current Status (determine at runtime):**
```bash
# Check currently deployed image:
kubectl -n tenant-ssc get deployment django-app-ssc \
  -o jsonpath='{.spec.template.spec.containers[0].image}'; echo

# Check your local HEAD:
git rev-parse --short HEAD
```

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
