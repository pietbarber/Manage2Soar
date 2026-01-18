# Email Delivery Fix: Internal IP and Firewall Rules

## Problem
Django pods in GKE cluster could not send emails through the mail server because:

1. **DNS Resolution Issue**: `mail.manage2soar.com` resolves to external IP (35.237.42.68), but GKE pods use internal VPC IPs
2. **Firewall Rule Gap**: The `m2s-mail-allow-smtp` firewall rule only allowed specific external IPs, not the GKE cluster's internal IP ranges

## Solution (Applied 2026-01-17)

### 1. Changed EMAIL_HOST to Internal IP
**File**: `group_vars/gcp_app/vars.yml` (gitignored)

```yaml
# Old:
mail_host: "mail.manage2soar.com"

# New:
mail_host: "<m2s-mail-internal-ip>"  # Use internal VPC IP of mail server
```

**Rationale**: Using the internal IP allows GKE pods to communicate with the mail server within the VPC, avoiding external IP routing and firewall complexity.

### 2. Added GKE IP Ranges to Firewall Rule
**File**: `group_vars/gcp_mail/vars.yml` (gitignored)

```yaml
# Old:
gcp_smtp_allowed_sources:
  - "<gke-node-1-external-ip>/32"
  - "<gke-node-2-external-ip>/32"
  - "<gke-node-3-external-ip>/32"

# New: Add GKE cluster internal IP ranges
gcp_smtp_allowed_sources:
  - "<gke-node-1-external-ip>/32"  # Existing node IPs
  - "<gke-node-2-external-ip>/32"
  - "<gke-node-3-external-ip>/32"
  - "<gke-pod-cidr>"               # GKE cluster pod IP range (check: gcloud container clusters describe)
  - "<gke-service-cidr>"           # GKE cluster service IP range
```

**Rationale**: The firewall rule `m2s-mail-allow-smtp` must allow traffic from GKE pod IPs, not just node external IPs.

## Manual Changes Already Applied
The following manual commands were run to fix the production environment before updating IaC:

```bash
# 1. Get GKE cluster IP ranges
gcloud container clusters describe <cluster-name> --zone=<zone> \
  --format="value(clusterIpv4Cidr,servicesIpv4Cidr)"

# 2. Updated firewall rule with GKE IP ranges
gcloud compute firewall-rules update m2s-mail-allow-smtp \
  --project=<project-id> \
  --source-ranges=<existing-ips>,<gke-pod-cidr>,<gke-service-cidr>

# 3. Updated Kubernetes secret with internal mail server IP
kubectl patch secret -n <namespace> <secret-name> \
  -p '{"data":{"EMAIL_HOST":"'$(echo -n "<mail-internal-ip>" | base64)'"}}'

# 4. Restarted deployment
kubectl rollout restart deployment -n <namespace> <deployment-name>
```

## Required Action
Update your local `group_vars/gcp_app/vars.yml` and `group_vars/gcp_mail/vars.yml` files with the changes above.

**To get the actual IP values:**
- Mail server internal IP: `gcloud compute instances describe <mail-instance> --zone=<zone> --format="value(networkInterfaces[0].networkIP)"`
- GKE cluster CIDRs: `gcloud container clusters describe <cluster-name> --zone=<zone> --format="value(clusterIpv4Cidr,servicesIpv4Cidr)"`

**Next deployment** will apply these settings automatically via Ansible playbooks.

## Verification
Test email delivery:
```bash
kubectl exec -n tenant-ssc deployment/django-app-ssc -- python manage.py shell -c "
from django.core.mail import send_mail
send_mail('Test', 'Test body', 'noreply@manage2soar.com', ['test@example.com'])
"
```

## Email Chain Flow
**Before Fix**: ❌ Django → mail.manage2soar.com (external IP) → ⏱️ TIMEOUT (firewall blocks GKE internal IPs)

**After Fix**: ✅ Django → mail server (internal VPC IP) → smtp2go → recipient
