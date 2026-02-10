# Admin Workstation Setup Guide

This guide will help you set up your workstation (Ubuntu/Debian or macOS) for deploying Manage2Soar to production (GKE/GCP).

## Quick Start - Automated Installation

We provide automated setup scripts for both platforms:

### Ubuntu/Debian:
```bash
./infrastructure/scripts/setup-admin-ubuntu.sh
```

### macOS (with Homebrew):
```bash
./infrastructure/scripts/setup-admin-homebrew.sh
```

These scripts will install all required and optional tools listed below. After running the script, follow the "Next Steps" section for authentication and configuration.

---

## Manual Installation (if needed)

If you prefer to install tools manually or need to troubleshoot the automated scripts, follow the instructions below for your platform.

## Prerequisites to Verify ✅

Before proceeding, ensure you have:

- Python 3.12+ with virtual environment support
- Git installed and configured
- Codebase cloned and accessible

Verify your environment:
```bash
python3 --version  # Should be 3.11 or higher
git --version      # Any recent version
```

## Required Tools 🔧

For production deployment, you need:

### Required for Production Deployment

1. **Google Cloud CLI (`gcloud`)** - GCP management
2. **kubectl** - Kubernetes cluster management
3. **Docker** - Build container images
4. **Ansible** - Infrastructure automation
5. **Ansible Collections** - kubernetes.core, google.cloud

### Optional but Recommended

6. **k9s** - Interactive Kubernetes cluster management
7. **helm** - Kubernetes package manager
8. **jq** - JSON parsing for scripts

---

## Installation Instructions (Ubuntu 24.04)

### 1. Install Google Cloud CLI

```bash
# Add Google Cloud SDK repo
sudo apt-get update
sudo apt-get install -y apt-transport-https ca-certificates gnupg curl

# Import Google Cloud public key
curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | sudo gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg

# Add gcloud apt repository
echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" | sudo tee -a /etc/apt/sources.list.d/google-cloud-sdk.list

# Install gcloud CLI
sudo apt-get update && sudo apt-get install -y google-cloud-cli google-cloud-cli-gke-gcloud-auth-plugin

# Initialize gcloud (this will open browser for auth)
gcloud init

# Authenticate for Docker (to push images to GCR)
gcloud auth configure-docker

# Set up application default credentials for Ansible
gcloud auth application-default login
```

**Verify:** `gcloud version` should show version info

### 2. Install kubectl

```bash
# Download latest stable kubectl
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"

# Make it executable and move to PATH
chmod +x kubectl
sudo mv kubectl /usr/local/bin/

# Verify installation
kubectl version --client
```

**Configure kubectl for your GKE cluster:**
```bash
# Get credentials for your GKE cluster (run after gcloud init)
gcloud container clusters get-credentials <CLUSTER_NAME> --region=<REGION> --project=<PROJECT_ID>

# Example:
# gcloud container clusters get-credentials manage2soar-cluster --region=us-east1 --project=manage2soar-prod
```

### 3. Install Docker

```bash
# Remove old Docker installations if any
for pkg in docker.io docker-doc docker-compose docker-compose-v2 podman-docker containerd runc; do
    sudo apt-get remove -y $pkg
done

# Add Docker's official GPG key
sudo apt-get update
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

# Add Docker repository
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker Engine
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Add your user to docker group (to run docker without sudo)
sudo usermod -aG docker $USER

# IMPORTANT: Log out and log back in for group membership to take effect
# Or run: newgrp docker
```

**Verify:** `docker run hello-world` should work without sudo

### 4. Install Ansible

```bash
# Install Ansible (Ubuntu 24.04 includes recent version)
sudo apt-get update
sudo apt-get install -y ansible

# Install required Ansible collections
ansible-galaxy collection install kubernetes.core
ansible-galaxy collection install google.cloud
ansible-galaxy collection install community.postgresql

# Verify installation
ansible --version
```

**Expected:** Ansible 2.16+ with Python 3.12

### 5. Install Optional Tools

```bash
# Install k9s (interactive Kubernetes CLI)
curl -sS https://webinstall.dev/k9s | bash
# Add to PATH (k9s installs to ~/.local/bin)
export PATH="$HOME/.local/bin:$PATH"
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc

# Install helm (Kubernetes package manager)
curl https://baltocdn.com/helm/signing.asc | gpg --dearmor | sudo tee /usr/share/keyrings/helm.gpg > /dev/null
sudo apt-get install apt-transport-https --yes
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/helm.gpg] https://baltocdn.com/helm/stable/debian/ all main" | sudo tee /etc/apt/sources.list.d/helm-stable-debian.list
sudo apt-get update
sudo apt-get install helm

# Install jq (JSON processor)
sudo apt-get install -y jq
```

---

## Configure Secrets & Credentials

### 1. Set up Ansible Vault Password

```bash
# Create vault password file (NEVER commit this!)
echo "your-secure-vault-password-here" > ~/.ansible_vault_pass
chmod 600 ~/.ansible_vault_pass
```

### 2. Copy Infrastructure Configuration Files

```bash
cd infrastructure/ansible

# Copy example files to create actual configs
cp inventory/gcp_app.yml.example inventory/gcp_app.yml
cp group_vars/gcp_app.vars.yml.example group_vars/gcp_app/vars.yml
cp group_vars/gcp_app.vault.yml.example group_vars/gcp_app/vault.yml

# Edit with your actual values
vim inventory/gcp_app.yml          # GCP project, region, cluster name
vim group_vars/gcp_app/vars.yml    # Non-secret configuration
vim group_vars/gcp_app/vault.yml   # Secrets (DB passwords, Django secret key, etc.)

# Encrypt the vault file
ansible-vault encrypt group_vars/gcp_app/vault.yml --vault-password-file ~/.ansible_vault_pass
```

### 3. GCP Service Account Setup

If you need a service account key (for CI/CD or non-interactive deployments):

```bash
# Create service account (if needed)
gcloud iam service-accounts create m2s-deployer \
    --display-name="Manage2Soar Deployer" \
    --project=<PROJECT_ID>

# Grant necessary roles
gcloud projects add-iam-policy-binding <PROJECT_ID> \
    --member="serviceAccount:m2s-deployer@<PROJECT_ID>.iam.gserviceaccount.com" \
    --role="roles/container.developer"

# Download key (store securely!)
gcloud iam service-accounts keys create ~/m2s-gcp-key.json \
    --iam-account=m2s-deployer@<PROJECT_ID>.iam.gserviceaccount.com

# Use with gcloud
export GOOGLE_APPLICATION_CREDENTIALS=~/m2s-gcp-key.json
```

---

## Deployment Workflows

### Full Application Deployment

```bash
cd ~/Projects/skylinesoaring/Manage2Soar/infrastructure/ansible

# Deploy everything (build, push, deploy to GKE)
ansible-playbook -i inventory/gcp_app.yml \
  --vault-password-file ~/.ansible_vault_pass \
  playbooks/gcp-app-deploy.yml
```

### Quick Deploy (Skip Image Build)

```bash
# Use existing Docker image, just update K8s deployment
ansible-playbook -i inventory/gcp_app.yml \
  --vault-password-file ~/.ansible_vault_pass \
  playbooks/gcp-app-deploy.yml \
  -e gke_build_image=false -e gke_push_image=false
```

### Update Secrets Only

```bash
ansible-playbook -i inventory/gcp_app.yml \
  --vault-password-file ~/.ansible_vault_pass \
  playbooks/gcp-app-deploy.yml --tags secrets
```

### Deploy Specific Tenant

```bash
# Deploy only to SSC namespace
ansible-playbook -i inventory/gcp_app.yml \
  --vault-password-file ~/.ansible_vault_pass \
  playbooks/gcp-app-deploy.yml \
  -e gke_deploy_tenant=ssc
```

---

## Verification Checklist

After setup, verify everything works:

### 1. GCP Connection
```bash
gcloud projects list
gcloud container clusters list
```

### 2. Kubernetes Access
```bash
kubectl get nodes
kubectl get namespaces
kubectl get pods --all-namespaces
```

### 3. Docker
```bash
docker ps
docker images
```

### 4. Ansible
```bash
ansible --version
ansible-galaxy collection list
```

### 5. Test Deployment (Dry Run)
```bash
cd infrastructure/ansible
ansible-playbook playbooks/gcp-app-deploy.yml \
  --vault-password-file ~/.ansible_vault_pass \
  --check --diff
```

---

## Common Issues & Troubleshooting

### Issue: `gcloud` command not found
**Solution:** Restart terminal or run `source ~/.bashrc`

### Issue: Docker permission denied
**Solution:** Log out and back in after adding user to docker group, or run `newgrp docker`

### Issue: kubectl can't connect to cluster
**Solution:**
```bash
gcloud container clusters get-credentials <CLUSTER> --region=<REGION>
kubectl config get-contexts
kubectl config use-context <CONTEXT_NAME>
```

### Issue: Ansible vault decryption fails
**Solution:** Verify ~/.ansible_vault_pass has correct password and `chmod 600` permissions

### Issue: Docker build fails in WSL
**Solution:** Make sure Docker Desktop is running with WSL2 integration enabled

---

## Security Best Practices

1. **Never commit secrets**:
   - `~/.ansible_vault_pass`
   - `infrastructure/ansible/inventory/gcp_app.yml`
   - `infrastructure/ansible/group_vars/gcp_app.vars.yml`
   - `infrastructure/ansible/group_vars/gcp_app.vault.yml` (unless encrypted)
   - `*.json` service account keys

2. **Use Ansible Vault** for all secrets in playbooks

3. **Rotate credentials regularly**:
   - GCP service account keys
   - Database passwords
   - Django SECRET_KEY

4. **Set file permissions**:
   ```bash
   chmod 600 ~/.ansible_vault_pass
   chmod 600 ~/m2s-gcp-key.json
   chmod 600 infrastructure/ansible/inventory/*.yml
   ```

5. **Use separate GCP projects** for prod/staging/dev

---

## Next Steps

Once your laptop is set up:

1. ✅ Install all required tools (see sections above)
2. ✅ Configure GCP authentication (`gcloud init`)
3. ✅ Get kubectl access to GKE cluster
4. ✅ Set up Ansible vault and configuration files
5. ✅ Run a test deployment (with `--check` flag first)
6. ✅ Deploy to production

For detailed deployment procedures, see:
- [infrastructure/docs/gcp-database-deployment.md](../infrastructure/docs/gcp-database-deployment.md)
- [infrastructure/README.md](../infrastructure/README.md)

---

## Quick Reference

```bash
# Check current context
kubectl config current-context

# Switch between clusters
kubectl config use-context <CONTEXT>

# View cluster info
kubectl cluster-info

# Get all resources in namespace
kubectl get all -n <NAMESPACE>

# Watch pod logs
kubectl logs -f deployment/django-app -n <NAMESPACE>

# Execute command in pod
kubectl exec -it deployment/django-app -n <NAMESPACE> -- python manage.py shell

# Port forward for debugging
kubectl port-forward deployment/django-app 8000:8000 -n <NAMESPACE>

# Rollback deployment
kubectl rollout undo deployment/django-app -n <NAMESPACE>

# View deployment history
kubectl rollout history deployment/django-app -n <NAMESPACE>
```
