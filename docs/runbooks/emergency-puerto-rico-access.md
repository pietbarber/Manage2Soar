# 🚨 Emergency Production Access from Puerto Rico (or anywhere)

**Date Created:** February 8, 2026  
**For:** Remote production access when away from home network

## Quick Access Methods (In Order of Preference)

### Method 1: Google Cloud Console (No local tools needed!)

**Access:** https://console.cloud.google.com/?project=manage2soar

1. **Check cluster health:**
   - GKE: https://console.cloud.google.com/kubernetes/list?project=manage2soar
   - Click `manage2soar-cluster` → Workloads → Check pods

2. **View logs:**
   - Click any deployment → Logs tab
   - Or: https://console.cloud.google.com/logs?project=manage2soar

3. **Emergency pod restart:**
   - Workloads → Click deployment → Actions → Rolling restart

4. **Check database:**
   - Compute Engine: https://console.cloud.google.com/compute/instances?project=manage2soar
   - Click `m2s-database` → SSH (opens browser SSH)

### Method 2: Cloud Shell (Built-in terminal in browser)

**Access:** https://shell.cloud.google.com/?project=manage2soar

Cloud Shell has `gcloud`, `kubectl`, `docker` pre-installed!

```bash
# Clone repo
git clone https://github.com/pietbarber/Manage2Soar.git
cd Manage2Soar

# Get kubectl access
gcloud container clusters get-credentials manage2soar-cluster \
  --zone=us-east1-b --project=manage2soar

# Check cluster status
kubectl get pods -n tenant-ssc
kubectl get pods -n tenant-masa

# View logs
kubectl logs -n tenant-ssc -l app=django-app-ssc --tail=100

# Emergency restart
kubectl rollout restart deployment/django-app-ssc -n tenant-ssc
kubectl rollout restart deployment/django-app-masa -n tenant-masa
```

### Method 3: Local Laptop (If you brought it)

#### Step 1: Get SSH Access from Your Puerto Rico IP

```bash
# Quick method - run the emergency script
./emergency-ssh-access.sh

# It will:
# 1. Get your current IP
# 2. Add it to firewall rules
# 3. Give you SSH access
```

**Manual method if script fails:**
```bash
# Get your IP
curl ifconfig.me

# Get current firewall source ranges
NEW_IP="YOUR_IP_HERE"

# 1) Read current ranges (always check live, don't copy from docs)
EXISTING=$(gcloud compute firewall-rules describe m2s-database-allow-ssh \
  --project=manage2soar --format='get(sourceRanges)' | tr ';' ',')

# 2) Update, appending your IP
gcloud compute firewall-rules update m2s-database-allow-ssh \
  --source-ranges="${EXISTING},${NEW_IP}/32" \
  --project=manage2soar

# Repeat for mail rule
EXISTING=$(gcloud compute firewall-rules describe m2s-mail-allow-ssh \
  --project=manage2soar --format='get(sourceRanges)' | tr ';' ',')

gcloud compute firewall-rules update m2s-mail-allow-ssh \
  --source-ranges="${EXISTING},${NEW_IP}/32" \
  --project=manage2soar
```

**Or via web console:**
1. Go to: https://console.cloud.google.com/net-security/firewall-manager/firewall-policies/list?project=manage2soar
2. Click `m2s-database-allow-ssh` → Edit
3. Add your IP with `/32` suffix to Source IP ranges
4. Repeat for `m2s-mail-allow-ssh`

#### Step 2: Use Ansible or kubectl

```bash
# Get kubectl access (one-time)
gcloud container clusters get-credentials manage2soar-cluster \
  --zone=us-east1-b --project=manage2soar

# Check cluster
kubectl get pods --all-namespaces

# Use Ansible
cd infrastructure/ansible
./test-connectivity.sh  # Verify you can reach servers
```

---

## 🔥 Emergency Procedures

### Issue: "Site is down / 502 Bad Gateway"

**Diagnosis via Cloud Console:**
1. GKE → Workloads → Check pod status
2. If pods show `CrashLoopBackOff` or `Error` → Check logs

**Quick Fix (Cloud Shell or local):**
```bash
# Check pods
kubectl get pods -n tenant-ssc
kubectl get pods -n tenant-masa

# View recent logs
kubectl logs -n tenant-ssc -l app=django-app-ssc --tail=100

# Emergency restart (safest fix for most issues)
kubectl rollout restart deployment/django-app-ssc -n tenant-ssc
kubectl rollout restart deployment/django-app-masa -n tenant-masa

# Watch rollout
kubectl rollout status deployment/django-app-ssc -n tenant-ssc
```

**If restart doesn't work - rollback to previous version:**
```bash
# Rollback both tenants
kubectl rollout undo deployment/django-app-ssc -n tenant-ssc
kubectl rollout undo deployment/django-app-masa -n tenant-masa
```

### Issue: "Database is slow / connections failing"

**Check database server (Cloud Console SSH to m2s-database):**
```bash
# Check PostgreSQL status
sudo systemctl status postgresql

# Check connections
sudo -u postgres psql -c "SELECT count(*) FROM pg_stat_activity;"

# Check for long-running queries
sudo -u postgres psql -c "SELECT pid, now() - query_start AS duration, query FROM pg_stat_activity WHERE state = 'active' ORDER BY duration DESC LIMIT 10;"

# Emergency: Kill long queries (if > 5 minutes)
sudo -u postgres psql -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE state = 'active' AND now() - query_start > interval '5 minutes';"

# Check disk space
df -h

# Check memory
free -h

# Restart PostgreSQL (last resort)
sudo systemctl restart postgresql
```

### Issue: "Need to deploy code fix"

**From Cloud Shell (easiest):**
```bash
git clone https://github.com/pietbarber/Manage2Soar.git
cd Manage2Soar

# Make your fix, commit, push to GitHub
# Then build and deploy:

# Get kubectl access
gcloud container clusters get-credentials manage2soar-cluster \
  --zone=us-east1-b --project=manage2soar

# Build image (Cloud Shell has Docker)
TIMESTAMP=$(date +%Y%m%d-%H%M)
GIT_HASH=$(git rev-parse --short HEAD)
IMAGE_TAG="${TIMESTAMP}-${GIT_HASH}"
FULL_IMAGE="gcr.io/manage2soar/manage2soar:${IMAGE_TAG}"

docker build -t "${FULL_IMAGE}" .
docker push "${FULL_IMAGE}"

# Update deployments
kubectl set image deployment/django-app-ssc \
    django="${FULL_IMAGE}" -n tenant-ssc
kubectl set image deployment/django-app-masa \
    django="${FULL_IMAGE}" -n tenant-masa

# Watch rollout
kubectl rollout status deployment/django-app-ssc -n tenant-ssc
```

**From local laptop (if you have Docker):**
```bash
# Same as above, but run locally
./quick-deploy.sh  # Uses the script you already have
```

### Issue: "Email not sending"

**Check mail server (Cloud Console SSH to m2s-mail):**
```bash
# Check Postfix status
sudo systemctl status postfix

# Check mail queue
mailq

# Check mail logs (last 50 lines)
sudo tail -50 /var/log/mail.log

# Flush mail queue (retry sending)
sudo postqueue -f

# Restart Postfix
sudo systemctl restart postfix

# Check if port 25 is blocked (common in hotels)
telnet smtp.gmail.com 25  # Should connect if outbound SMTP works
```

### Issue: "SSL certificate expired"

This shouldn't happen (Let's Encrypt auto-renews), but if it does:

**Via kubectl:**
```bash
# Check cert-manager (handles auto-renewal)
kubectl get certificates --all-namespaces

# Trigger manual renewal
kubectl delete certificaterequest --all --all-namespaces

# Check after 2 minutes
kubectl get certificates --all-namespaces
```

---

## 🔍 Monitoring & Health Checks

### Check Everything is Running

**Quick health check (Cloud Shell):**
```bash
# Cluster nodes
kubectl get nodes

# All pods
kubectl get pods --all-namespaces | grep -v "Running\|Completed"

# Services and ingress
kubectl get gateway,httproute -A

# Recent events (errors will show here)
kubectl get events --all-namespaces --sort-by='.lastTimestamp' | tail -20
```

### View Application Logs

```bash
# Last 100 lines from SSC tenant
kubectl logs -n tenant-ssc -l app=django-app-ssc --tail=100

# Follow logs in real-time
kubectl logs -n tenant-ssc -l app=django-app-ssc -f

# Check CronJob logs
kubectl logs -n tenant-ssc $(kubectl get pods -n tenant-ssc | grep clearsessions | tail -1 | awk '{print $1}')
```

### Check Resource Usage

```bash
# Node resource usage
kubectl top nodes

# Pod resource usage
kubectl top pods --all-namespaces

# Database server disk space (via gcloud compute ssh)
gcloud compute ssh m2s-database --zone=us-east1-b --project=manage2soar -- "df -h && free -h"
```

---

## 📱 Access from Your Phone (Emergency Only)

1. **Install Termux** (Android) or **iSH Shell** (iOS)
2. **Install gcloud:**
   ```bash
   # In Termux/iSH
   curl https://sdk.cloud.google.com | bash
   gcloud init
   ```
3. **Use Cloud Shell instead:** Just open https://shell.cloud.google.com in mobile browser

---

## ✅ Pre-Trip Checklist

Before you leave for Puerto Rico:

- [ ] Commit and push all code changes to GitHub
- [ ] Test `./emergency-ssh-access.sh` works from your laptop
- [ ] Verify you can access Google Cloud Console on phone
- [ ] Bookmark these URLs on phone:
  - https://console.cloud.google.com/?project=manage2soar
  - https://shell.cloud.google.com/?project=manage2soar
  - https://github.com/pietbarber/Manage2Soar
- [ ] Save this runbook as PDF on phone
- [ ] Make sure phone has gcloud authenticator app (if using 2FA)
- [ ] Test you can clone repository and run `quick-deploy.sh`

---

## 🏖️ When You Return Home

Don't forget to clean up your Puerto Rico IP:

```bash
# Remove your Puerto Rico IP from firewall rules
# First, get current ranges:
gcloud compute firewall-rules describe m2s-database-allow-ssh \
  --project=manage2soar --format='get(sourceRanges)'

# Update with the ranges MINUS your travel IP:
gcloud compute firewall-rules update m2s-database-allow-ssh \
  --source-ranges="<PASTE_RANGES_WITHOUT_TRAVEL_IP>" \
  --project=manage2soar

# Repeat for mail rule:
gcloud compute firewall-rules describe m2s-mail-allow-ssh \
  --project=manage2soar --format='get(sourceRanges)'

gcloud compute firewall-rules update m2s-mail-allow-ssh \
  --source-ranges="<PASTE_RANGES_WITHOUT_TRAVEL_IP>" \
  --project=manage2soar
```

---

## 🆘 Nuclear Option (If Nothing Else Works)

**Scale pods to 3 (more redundancy):**
```bash
kubectl scale deployment/django-app-ssc --replicas=3 -n tenant-ssc
kubectl scale deployment/django-app-masa --replicas=3 -n tenant-masa
```

**Put up a maintenance page:**
```bash
# Create temporary maintenance page deployment
# (You'll need to create this YAML and have it ready)
```

**Call for help:**
- GitHub Issues: Post issue describing problem
- Your co-webmaster contact (if you have one)
- GCP Support (if critical and you have a support plan)

---

## 📞 Important Links

- **GCP Console:** https://console.cloud.google.com/?project=manage2soar
- **Cloud Shell:** https://shell.cloud.google.com
- **GitHub Repo:** https://github.com/pietbarber/Manage2Soar
- **GKE Cluster:** https://console.cloud.google.com/kubernetes/clusters/details/us-east1-b/manage2soar-cluster?project=manage2soar
- **Firewall Rules:** https://console.cloud.google.com/net-security/firewall-manager/firewall-policies/list?project=manage2soar
- **Logs:** https://console.cloud.google.com/logs?project=manage2soar

---

**🌴 Enjoy Puerto Rico and try not to check on the site too often! 🌴**
