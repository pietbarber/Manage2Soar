# Troubleshooting Guide

Common production issues, symptoms, diagnosis, and fixes for Manage2Soar deployments.

## 📖 Overview

This guide follows a **Symptom → Diagnosis → Fix** workflow for rapid incident response. Each section includes IaC-first remediation steps.

## 🚨 Emergency Quick Checks

When something goes wrong, run these first:

```bash
# Pod status
kubectl get pods -n tenant-ssc
kubectl get pods -n tenant-masa

# Recent errors
kubectl logs -n tenant-ssc deployment/django-app-ssc --tail=100 | grep -i error

# Database connectivity
kubectl exec -n tenant-ssc deployment/django-app-ssc -- \
  python manage.py check --database default

# Site accessibility
curl -I https://ssc.manage2soar.com/
curl -I https://masa.manage2soar.com/
```

---

## Database Connection Issues

### Authentication Failed

**Symptom**:
```
Internal Server Error (500)
FATAL: password authentication failed for user "m2s_ssc"
```

**Diagnosis**:
```bash
# Check database host/credentials in K8s secret
kubectl get secret manage2soar-env-ssc -n tenant-ssc -o yaml

# Decode password
kubectl get secret manage2soar-env-ssc -n tenant-ssc \
  -o jsonpath='{.data.DB_PASSWORD}' | base64 -d && echo

# Check vault password
cd infrastructure/ansible
ansible-vault view group_vars/gcp_database/vault.yml \
  --vault-password-file ~/.ansible_vault_pass | grep vault_postgresql_password_ssc
```

**Root Cause**: Mismatch between PostgreSQL user password and K8s secret

**Fix (IaC Approach)**:

1. Update password in vault:
```bash
cd infrastructure/ansible
ansible-vault edit group_vars/gcp_database/vault.yml \
  --vault-password-file ~/.ansible_vault_pass
```

2. Apply to database:
```bash
ansible-playbook -i inventory/gcp_database.yml \
  --vault-password-file ~/.ansible_vault_pass \
  playbooks/gcp-database.yml --tags postgresql
```

3. Update K8s secrets:
```bash
ansible-playbook -i inventory/gcp_app.yml \
  --vault-password-file ~/.ansible_vault_pass \
  playbooks/gcp-app-deploy.yml --tags secrets
```

4. Restart pods:
```bash
kubectl rollout restart deployment/django-app-ssc -n tenant-ssc
kubectl rollout restart deployment/django-app-masa -n tenant-masa
```

**Emergency Manual Fix** (follow with IaC):
```bash
# SSH to database server
gcloud compute ssh m2s-database --zone=us-east1-b --project=manage2soar

# Connect as postgres user
sudo -u postgres psql

# Reset password (use password from vault)
ALTER USER m2s_ssc WITH PASSWORD 'password_from_vault';
ALTER USER m2s_masa WITH PASSWORD 'password_from_vault';
\q
exit

# Restart application pods
kubectl rollout restart deployment/django-app-ssc -n tenant-ssc
```

**Verification**:
```bash
# Test database connection
kubectl exec -n tenant-ssc deployment/django-app-ssc -- \
  python manage.py check --database default

# Verify site works
curl -I https://ssc.manage2soar.com/
```

**Prevention**: Always use Ansible to manage database passwords. Never set passwords manually without updating vault.

---

### Connection Refused

**Symptom**:
```
OperationalError: could not connect to server: Connection refused
Is the server running on host "10.0.0.7" and accepting TCP/IP connections on port 5432?
```

**Diagnosis**:
```bash
# Check PostgreSQL status
gcloud compute ssh m2s-database --zone=us-east1-b \
  --command "systemctl status postgresql"

# Check port listening
gcloud compute ssh m2s-database --zone=us-east1-b \
  --command "sudo netstat -tlnp | grep 5432"

# Check firewall rules
gcloud compute firewall-rules list --filter="name~'m2s-database'"
```

**Root Causes**:
1. PostgreSQL service down
2. Wrong database host IP
3. Firewall blocking connections
4. PostgreSQL not listening on correct interface

**Fix**:

**If PostgreSQL is down**:
```bash
gcloud compute ssh m2s-database --zone=us-east1-b \
  --command "sudo systemctl restart postgresql"
```

**If firewall issue**:
```bash
# Check current rules
gcloud compute firewall-rules describe m2s-database-allow-gke

# Re-apply with Ansible
cd infrastructure/ansible
ansible-playbook -i inventory/gcp_database.yml \
  --vault-password-file ~/.ansible_vault_pass \
  playbooks/gcp-database.yml --tags gcp-provision
```

**If wrong host IP**:
```bash
# Get actual database IP
gcloud compute instances describe m2s-database \
  --zone=us-east1-b --format='get(networkInterfaces[0].networkIP)'

# Update vault with correct IP
cd infrastructure/ansible
ansible-vault edit group_vars/gcp_app/vault.yml \
  --vault-password-file ~/.ansible_vault_pass

# Update secrets
ansible-playbook -i inventory/gcp_app.yml \
  --vault-password-file ~/.ansible_vault_pass \
  playbooks/gcp-app-deploy.yml --tags secrets
```

---

### Too Many Connections

**Symptom**:
```
OperationalError: FATAL: sorry, too many clients already
```

**Diagnosis**:
```bash
# Check current connections
gcloud compute ssh m2s-database --zone=us-east1-b

sudo -u postgres psql -c "SELECT count(*) FROM pg_stat_activity;"
sudo -u postgres psql -c "SELECT datname, count(*) FROM pg_stat_activity GROUP BY datname;"
```

**Quick Fix**:
```bash
# Kill idle connections (emergency only)
sudo -u postgres psql << 'EOF'
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE state = 'idle'
AND state_change < now() - interval '30 minutes';
EOF
```

**Permanent Fix**:
```bash
# Increase max_connections in PostgreSQL
cd infrastructure/ansible
ansible-vault edit group_vars/gcp_database/vars.yml

# Update: postgresql_max_connections: 300

# Apply changes
ansible-playbook -i inventory/gcp_database.yml \
  --vault-password-file ~/.ansible_vault_pass \
  playbooks/gcp-database.yml --tags postgresql
```

---

## Pod Failures

### CrashLoopBackOff

**Symptom**: Pod repeatedly crashes and restarts

```bash
kubectl get pods -n tenant-ssc
# NAME                              READY   STATUS             RESTARTS
# django-app-ssc-7d9f8b5c4d-k8m2j   0/1     CrashLoopBackOff   5
```

**Diagnosis**:
```bash
# View pod logs
kubectl logs -n tenant-ssc deployment/django-app-ssc --tail=100

# Check previous crash logs
kubectl logs -n tenant-ssc <pod-name> --previous

# Describe pod for events
kubectl describe pod <pod-name> -n tenant-ssc
```

**Common Causes**:

1. **Database connection failure**: See [Authentication Failed](#authentication-failed)

2. **Missing environment variables**:
```bash
# Check secret exists
kubectl get secret manage2soar-env-ssc -n tenant-ssc

# Verify required keys
kubectl get secret manage2soar-env-ssc -n tenant-ssc -o jsonpath='{.data}' | jq 'keys'
```

3. **Application error on startup**:
```bash
# Check Python errors in logs
kubectl logs -n tenant-ssc <pod-name> | grep -A 10 "Traceback"

# Test startup locally
docker run --rm -it gcr.io/manage2soar/django-app:latest python manage.py check
```

**Fix**:
```bash
# Update secrets
ansible-playbook -i inventory/gcp_app.yml \
  --vault-password-file ~/.ansible_vault_pass \
  playbooks/gcp-app-deploy.yml --tags secrets

# If code issue, rollback
kubectl rollout undo deployment/django-app-ssc -n tenant-ssc
```

---

### ImagePullBackOff

**Symptom**: Cannot pull Docker image from GCR

```bash
kubectl get pods -n tenant-ssc
# NAME                              READY   STATUS              RESTARTS
# django-app-ssc-7d9f8b5c4d-k8m2j   0/1     ImagePullBackOff    0
```

**Diagnosis**:
```bash
# Check exact error
kubectl describe pod <pod-name> -n tenant-ssc | grep -A 5 "Events:"

# Common errors:
# - "unauthorized: authentication required"
# - "manifest unknown: image not found"
# - "denied: Permission denied"
```

**Fix**:

**If image doesn't exist**:
```bash
# Rebuild and push image
cd infrastructure/ansible
ansible-playbook -i inventory/gcp_app.yml \
  --vault-password-file ~/.ansible_vault_pass \
  playbooks/gcp-app-deploy.yml
```

**If authentication issue**:
```bash
# Re-configure Docker authentication
gcloud auth configure-docker

# Check GKE node has GCR access
gcloud container clusters describe m2s-gke-prod \
  --zone=us-east1-b --format='get(nodeConfig.oauthScopes)' | grep storage-ro
```

---

### Pending (Resource Constraints)

**Symptom**: Pod stuck in Pending state

**Diagnosis**:
```bash
# Check why pending
kubectl describe pod <pod-name> -n tenant-ssc | grep -A 10 "Events:"

# Common reasons:
# - Insufficient CPU
# - Insufficient memory
# - No nodes available
```

**Fix**:

**If insufficient resources**:
```bash
# Check node resources
kubectl top nodes

# Check resource requests
kubectl describe deployment django-app-ssc -n tenant-ssc | grep -A 5 "Requests:"

# Reduce resource requests in deployment manifest
```

**If no nodes available**:
```bash
# Scale up node pool
gcloud container clusters resize m2s-gke-prod \
  --zone=us-east1-b --num-nodes=3

# Or add new node pool
gcloud container node-pools create larger-pool \
  --cluster=m2s-gke-prod --zone=us-east1-b \
  --num-nodes=2 --machine-type=e2-standard-2
```

---

## CronJob Failures

### CronJob Not Running

**Symptom**: Scheduled tasks not executing

**Diagnosis**:
```bash
# Check CronJob status
kubectl get cronjobs -n tenant-ssc

# Check recent jobs
kubectl get jobs -n tenant-ssc --sort-by=.status.startTime

# View CronJob details
kubectl describe cronjob <cronjob-name> -n tenant-ssc
```

**Common Causes**:

1. **CronJob suspended**:
```bash
# Check if suspended
kubectl get cronjob <cronjob-name> -n tenant-ssc -o jsonpath='{.spec.suspend}'

# Unsuspend
kubectl patch cronjob <cronjob-name> -n tenant-ssc -p '{"spec":{"suspend":false}}'
```

2. **Failed previous job**:
```bash
# Check job logs
kubectl logs job/<job-name> -n tenant-ssc

# Delete failed job
kubectl delete job <job-name> -n tenant-ssc
```

---

### Distributed Lock Timeout

**Symptom**: CronJob logs show lock acquisition failure

```
ERROR: Could not acquire lock for send_daily_digest. Another pod may be running this task.
```

**Diagnosis**:
```bash
# Check active locks in database
kubectl exec -n tenant-ssc deployment/django-app-ssc -- \
  python manage.py shell << 'EOF'
from utils.models import CronJobLock
for lock in CronJobLock.objects.all():
    print(f"{lock.job_name}: acquired={lock.acquired_at}, by={lock.acquired_by}")
EOF
```

**Fix**:

**If stale lock (pod crashed mid-execution)**:
```bash
# Clear stale locks (older than 1 hour)
kubectl exec -n tenant-ssc deployment/django-app-ssc -- \
  python manage.py shell << 'EOF'
from utils.models import CronJobLock
from django.utils import timezone
import datetime

stale_time = timezone.now() - datetime.timedelta(hours=1)
stale_locks = CronJobLock.objects.filter(acquired_at__lt=stale_time)
print(f"Clearing {stale_locks.count()} stale locks")
stale_locks.delete()
EOF
```

**See**: [CronJob Architecture](../cronjob-architecture.md) for complete troubleshooting

---

## Static File Issues

### 404 on Static Files

**Symptom**: CSS/JS not loading, browser shows 404

**Diagnosis**:
```bash
# Test static file serving
curl -I https://ssc.manage2soar.com/static/css/baseline.css

# Check if collectstatic ran
kubectl exec -n tenant-ssc deployment/django-app-ssc -- \
  ls -la /app/staticfiles/css/baseline.css

# Check GCS bucket
gsutil ls gs://skyline-soaring-storage/static/
```

**Fix**:

**If collectstatic didn't run**:
```bash
# Manual collection
kubectl exec -n tenant-ssc deployment/django-app-ssc -- \
  python manage.py collectstatic --noinput

# IaC fix: Rebuild image (collectstatic happens during build)
cd infrastructure/ansible
ansible-playbook -i inventory/gcp_app.yml \
  --vault-password-file ~/.ansible_vault_pass \
  playbooks/gcp-app-deploy.yml
```

**If GCS permission issue**:
```bash
# Check GCS bucket permissions
gsutil iam get gs://skyline-soaring-storage/

# Re-apply storage playbook
cd infrastructure/ansible
ansible-playbook -i inventory/gcp_storage.yml \
  playbooks/gcp-storage.yml
```

---

### CSS Changes Not Visible

**Symptom**: Updated CSS not appearing in browser

**Root Cause**: `collectstatic` not run after CSS changes

**Fix**:
```bash
# ALWAYS run collectstatic after CSS changes
cd /path/to/Manage2Soar
source .venv/bin/activate
python manage.py collectstatic --noinput

# Deploy updated static files
cd infrastructure/ansible
ansible-playbook -i inventory/gcp_app.yml \
  --vault-password-file ~/.ansible_vault_pass \
  playbooks/gcp-app-deploy.yml
```

**See**: `.github/copilot-instructions.md` - CSS & Static Files Management

---

## SSL/TLS Issues

### Certificate Expired

**Symptom**: Browser shows "Your connection is not private"

**Diagnosis**:
```bash
# Check certificate expiry
curl -vI https://ssc.manage2soar.com/ 2>&1 | grep "expire"

# Check managed certificate status
kubectl get managedcertificate -n tenant-ssc
```

**Fix**:

**If managed certificate (Google):**
```bash
# Managed certs auto-renew, check status
kubectl describe managedcertificate m2s-managed-cert -n tenant-ssc

# If failed, recreate
kubectl delete managedcertificate m2s-managed-cert -n tenant-ssc
kubectl apply -f managed-cert.yaml
```

**If Let's Encrypt (single-host):**
```bash
# Renew certificate
sudo certbot renew

# Restart nginx
sudo systemctl restart nginx
```

---

### SSL Handshake Failure

**Symptom**: `SSL: CERTIFICATE_VERIFY_FAILED`

**Diagnosis**:
```bash
# Test SSL connection
openssl s_client -connect ssc.manage2soar.com:443 -servername ssc.manage2soar.com

# Check certificate chain
curl -v https://ssc.manage2soar.com/ 2>&1 | grep -A 10 "SSL certificate"
```

**Common Causes**:
1. Certificate chain incomplete
2. Certificate doesn't match domain
3. Mixed HTTP/HTTPS content

**Fix**: See [GKE Gateway Ingress Guide](../../infrastructure/ansible/docs/gke-gateway-ingress-guide.md)

---

## Performance Issues

### Slow Response Times

**Symptom**: Pages taking >3 seconds to load

**Diagnosis**:
```bash
# Check response times
time curl -I https://ssc.manage2soar.com/

# Check pod CPU/memory
kubectl top pods -n tenant-ssc

# Check database query performance
kubectl exec -n tenant-ssc deployment/django-app-ssc -- \
  python manage.py shell << 'EOF'
from django.db import connection
from django.db import reset_queries
from django.conf import settings
settings.DEBUG = True

# Run slow query
# ...

print(f"Total queries: {len(connection.queries)}")
for q in connection.queries:
    if float(q['time']) > 0.5:
        print(f"SLOW: {q['time']}s - {q['sql'][:100]}")
EOF
```

**Quick Fixes**:

**Scale up pods**:
```bash
# Increase replicas
kubectl scale deployment django-app-ssc -n tenant-ssc --replicas=3
```

**Restart pods (clear memory leaks)**:
```bash
kubectl rollout restart deployment/django-app-ssc -n tenant-ssc
```

**Database connection pooling**:
```bash
# Check active connections
gcloud compute ssh m2s-database --zone=us-east1-b \
  --command "sudo -u postgres psql -c 'SELECT count(*) FROM pg_stat_activity;'"

# Restart to clear idle connections
kubectl rollout restart deployment/django-app-ssc -n tenant-ssc
```

**See**: [docs/performance-optimization-issue-285.md](../performance-optimization-issue-285.md)

---

### High Memory Usage

**Symptom**: Pods getting OOMKilled

**Diagnosis**:
```bash
# Check memory usage
kubectl top pods -n tenant-ssc

# Check pod events for OOMKilled
kubectl get events -n tenant-ssc --field-selector reason=OOMKilling

# Check memory limits
kubectl describe deployment django-app-ssc -n tenant-ssc | grep -A 3 "Limits:"
```

**Fix**:

**Increase memory limits**:
```bash
# Edit Ansible deployment role
vim infrastructure/ansible/roles/gke-deploy/defaults/main.yml

# Update:
gke_memory_limit: 2Gi  # Increase from 1Gi
gke_memory_request: 1Gi  # Increase from 512Mi

# Apply via Ansible (IaC-first approach)
ansible-playbook infrastructure/ansible/gke-deploy.yml
```

---

## Log Analysis

### Finding Recent Errors

```bash
# Last 100 lines with errors
kubectl logs -n tenant-ssc deployment/django-app-ssc --tail=100 | grep -i error

# Errors in last hour
kubectl logs -n tenant-ssc deployment/django-app-ssc --since=1h | grep -i error

# Python tracebacks
kubectl logs -n tenant-ssc deployment/django-app-ssc --tail=1000 | grep -A 10 "Traceback"

# Database errors
kubectl logs -n tenant-ssc deployment/django-app-ssc | grep -i "operationalerror\|databaseerror"
```

### Export Logs for Analysis

```bash
# Export to file
kubectl logs -n tenant-ssc deployment/django-app-ssc > /tmp/ssc-logs.txt

# All pods in namespace (both tenants)
for ns in tenant-ssc tenant-masa; do
  for pod in $(kubectl get pods -n $ns -o name); do
    echo "=== $ns/$pod ===" >> /tmp/all-logs.txt
    kubectl logs -n $ns $pod >> /tmp/all-logs.txt
  done
done
```

---

## Health Check Commands

### Quick System Health

```bash
#!/bin/bash
# health-check.sh

echo "=== Pod Status ==="
kubectl get pods -n tenant-ssc
kubectl get pods -n tenant-masa

echo -e "\n=== Recent Errors ==="
kubectl logs -n tenant-ssc deployment/django-app-ssc --tail=20 | grep -i error || echo "No errors"

echo -e "\n=== Database Status ==="
gcloud compute ssh m2s-database --zone=us-east1-b \
  --command "systemctl is-active postgresql" || echo "Database issue!"

echo -e "\n=== Site Accessibility ==="
curl -s -o /dev/null -w "SSC: %{http_code}\n" https://ssc.manage2soar.com/
curl -s -o /dev/null -w "MASA: %{http_code}\n" https://masa.manage2soar.com/

echo -e "\n=== CronJobs ==="
kubectl get cronjobs -n tenant-ssc
kubectl get cronjobs -n tenant-masa
```

---

## Escalation Path

1. **Check this runbook**: Most issues covered here
2. **Check pod logs**: `kubectl logs -n tenant-ssc deployment/django-app-ssc`
3. **Check database**: SSH to m2s-database, check PostgreSQL
4. **Check GKE console**: https://console.cloud.google.com/kubernetes
5. **Rollback if critical**: `kubectl rollout undo deployment/django-app-ssc`
6. **Document incident**: Update runbook with new scenarios

---

## References

- [Deployment & Updates](deployment-updates.md)
- [Ansible Playbook Guide](ansible-playbook-guide.md)
- [CronJob Architecture](../cronjob-architecture.md)
- [GKE Post-Deployment](../../infrastructure/ansible/docs/gke-post-deployment.md)
- Database Operations Runbook (planned for future)

---

**Last Updated**: January 17, 2026  
**Maintained By**: Infrastructure Team
