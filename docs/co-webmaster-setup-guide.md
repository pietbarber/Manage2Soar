# Co-Webmaster Setup Guide

This guide helps new co-webmasters get set up with full access to the Manage2Soar infrastructure.

## Overview

You'll get access to:
- **GKE Cluster** (Kubernetes) - Django application pods
- **Compute VMs** - Database server (`m2s-database`) and mail server (`m2s-mail`)
- **Monitoring & Logs** - CloudWatch-style monitoring and application logs
- **Storage** - Google Cloud Storage buckets
- **Container Registry** - Docker images

## Prerequisites

- Google account (Gmail or Google Workspace)
- Terminal/command line familiarity
- SSH key pair (we'll generate if needed)

---

## Step 1: Install Google Cloud CLI

### macOS

**Option A: Using Homebrew (Recommended)**
```bash
brew install google-cloud-sdk
```

**Option B: Direct Install**
```bash
curl https://sdk.cloud.google.com | bash
exec -l $SHELL
```

### Linux (Debian/Ubuntu)

```bash
# Add Cloud SDK repository
echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" | sudo tee -a /etc/apt/sources.list.d/google-cloud-sdk.list

# Import Google Cloud public key
curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | sudo gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg

# Update and install
sudo apt-get update
sudo apt-get install google-cloud-cli
sudo apt-get install google-cloud-cli-gke-gcloud-auth-plugin
sudo apt-get install kubectl
```

### Linux (Other Distributions)

```bash
curl https://sdk.cloud.google.com | bash
exec -l $SHELL
```

---

## Step 2: Generate SSH Key (if needed)

If you don't already have an SSH key:

```bash
# Generate new SSH key
ssh-keygen -t rsa -b 4096 -C "your.email@example.com"

# Press Enter to accept default location (~/.ssh/id_rsa)
# Enter a passphrase when prompted (recommended)

# Verify key was created
ls -la ~/.ssh/id_rsa*
```

You should see:
- `~/.ssh/id_rsa` (private key - NEVER share this)
- `~/.ssh/id_rsa.pub` (public key - safe to share)

---

## Step 3: Initialize gcloud

```bash
# Initialize gcloud (opens browser for authentication)
gcloud init

# When prompted:
# 1. Choose "Log in with a new account"
# 2. Select project: manage2soar
# 3. Choose default region: us-east1
# 4. Choose default zone: us-east1-b
```

**Verify authentication:**
```bash
gcloud auth list
# Should show your email with an asterisk (*)
```

---

## Step 4: Set Up Project Access

```bash
# Set project explicitly
gcloud config set project manage2soar

# Verify project is set
gcloud config get-value project
# Should output: manage2soar
```

---

## Step 5: Install kubectl

```bash
# Install kubectl component
gcloud components install kubectl

# Get GKE cluster credentials
gcloud container clusters get-credentials manage2soar-cluster --zone=us-east1-b

# Verify kubectl access
kubectl get nodes
# Should show 3 nodes running
```

---

## Step 6: Set Up SSH Access to VMs

```bash
# Add your SSH key for OS Login
gcloud compute os-login ssh-keys add --key-file ~/.ssh/id_rsa.pub

# Test SSH access to database server
gcloud compute ssh m2s-database --zone=us-east1-b

# Exit and test mail server
exit
gcloud compute ssh m2s-mail --zone=us-east1-b
exit
```

**Troubleshooting SSH:**
If you get "Permission denied" errors:
1. Wait 1-2 minutes for IAM propagation
2. Try again with `--tunnel-through-iap` flag:
   ```bash
   gcloud compute ssh m2s-database --zone=us-east1-b --tunnel-through-iap
   ```

---

## Step 7: Verify Full Access

Run these commands to verify everything works:

```bash
# List all VMs
gcloud compute instances list

# List all pods across all tenants
kubectl get pods --all-namespaces

# View logs from a pod
kubectl logs -n tenant-ssc -l app=django-app-ssc --tail=50

# Execute command in a pod
kubectl exec -n tenant-ssc -l app=django-app-ssc -- python manage.py showmigrations

# List storage buckets
gsutil ls

# View monitoring metrics (opens in browser)
gcloud monitoring dashboards list
```

---

## Common Tasks

### Deploy Changes (using Ansible)

```bash
# Clone the repository
git clone https://github.com/pietbarber/Manage2Soar.git
cd Manage2Soar

# Set up Python virtual environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run deployment (requires vault password)
cd infrastructure/ansible
ansible-playbook -i inventory/gcp_app.yml \
  --vault-password-file ~/.ansible_vault_pass \
  playbooks/gcp-app-deploy.yml
```

**Note:** You'll need the Ansible vault password from Piet.

### Run Migrations

```bash
# Get a pod name
kubectl get pods -n tenant-ssc -l app=django-app-ssc

# Run migrations
kubectl exec -n tenant-ssc <pod-name> -- python manage.py migrate
```

### View Application Logs

```bash
# Real-time logs for SSC tenant
kubectl logs -n tenant-ssc -l app=django-app-ssc -f

# Last 100 lines
kubectl logs -n tenant-ssc -l app=django-app-ssc --tail=100

# Logs from specific pod
kubectl logs -n tenant-ssc <pod-name>
```

### Restart Pods

```bash
# Restart all pods in SSC tenant
kubectl rollout restart deployment/django-app-ssc -n tenant-ssc

# Restart MASA tenant
kubectl rollout restart deployment/django-app-masa -n tenant-masa

# Check rollout status
kubectl rollout status deployment/django-app-ssc -n tenant-ssc
```

### SSH to Database Server

```bash
# Connect to database VM
gcloud compute ssh m2s-database --zone=us-east1-b

# Once connected, access PostgreSQL
sudo -u postgres psql

# Connect to specific database
\c ssc_manage2soar

# List tables
\dt

# Exit
\q
exit
```

### Check Application Status

```bash
# Check pod health
kubectl get pods -n tenant-ssc -l app=django-app-ssc

# Check deployment status
kubectl describe deployment django-app-ssc -n tenant-ssc

# Check service endpoints
kubectl get svc -n tenant-ssc

# Check ingress
kubectl get ingress --all-namespaces
```

---

## Project Structure

```
Manage2Soar/
├── infrastructure/
│   └── ansible/           # Deployment automation
│       ├── inventory/     # GCP configuration
│       ├── playbooks/     # Deployment playbooks
│       └── roles/         # Ansible roles
├── k8s-*.yaml            # Kubernetes manifests
├── members/              # Django members app
├── logsheet/             # Flight logging
├── duty_roster/          # Duty officer scheduling
└── docs/                 # Documentation
```

---

## Important URLs

- **SSC Production**: https://skylinesoaring.org/
- **SSC Alternate**: https://ssc.manage2soar.com/
- **MASA Staging**: https://masa.manage2soar.com/
- **GCP Console**: https://console.cloud.google.com/
- **GitHub Repo**: https://github.com/pietbarber/Manage2Soar

---

## Security Best Practices

1. **Never commit secrets** - Use Ansible Vault for sensitive data
2. **Use SSH keys** - Never use password authentication
3. **Enable 2FA** - On your Google account
4. **Keep gcloud updated** - Run `gcloud components update` regularly
5. **Use kubectl contexts** - Always verify you're in the right context
6. **Review changes** - Always review code before deploying

---

## Getting Help

- **Project Lead**: Piet Barber (pb@pietbarber.com)
- **Documentation**: `/docs/` directory in repo
- **Architecture Docs**: `docs/workflows/` for business processes
- **Runbooks**: `docs/runbooks/` for operational procedures

---

## Troubleshooting

### "Permission denied" errors
- Wait 1-2 minutes for IAM changes to propagate
- Run `gcloud auth login` to refresh credentials
- Check project: `gcloud config get-value project`

### kubectl connection issues
- Re-authenticate: `gcloud container clusters get-credentials manage2soar-cluster --zone=us-east1-b`
- Check context: `kubectl config current-context`

### SSH key issues
- Re-add key: `gcloud compute os-login ssh-keys add --key-file ~/.ssh/id_rsa.pub`
- List keys: `gcloud compute os-login ssh-keys list`
- Try IAP tunnel: `gcloud compute ssh <vm-name> --tunnel-through-iap`

### Ansible vault password
- Contact Piet for the vault password
- Store in `~/.ansible_vault_pass` (gitignored)
- Never commit this file!

---

## Next Steps

1. ✅ Complete all setup steps above
2. ✅ Clone the GitHub repository
3. ✅ Get Ansible vault password from Piet
4. ✅ Review the architecture docs in `/docs/`
5. ✅ Join the team Slack/communication channel
6. ✅ Shadow a deployment to learn the process

Welcome to the team! 🎉
