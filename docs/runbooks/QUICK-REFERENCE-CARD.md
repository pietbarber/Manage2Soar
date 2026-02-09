# 🚨 Emergency Access Quick Reference Card

**Print this or save to phone!**

---

## 🌐 Emergency Access (No Local Tools Needed)

**Browser Console:** https://console.cloud.google.com/?project=manage2soar  
**Cloud Shell:** https://shell.cloud.google.com/?project=manage2soar  
**GitHub Repo:** https://github.com/pietbarber/Manage2Soar

---

## 🔥 Most Common Fixes

### Site Down? Restart Pods (Cloud Shell)
```bash
gcloud container clusters get-credentials manage2soar-cluster --zone=us-east1-b --project=manage2soar
kubectl rollout restart deployment/django-app-ssc -n tenant-ssc
kubectl rollout restart deployment/django-app-masa -n tenant-masa
```

### Check Status
```bash
kubectl get pods -n tenant-ssc
kubectl get pods -n tenant-masa
kubectl logs -n tenant-ssc -l app=django-app-ssc --tail=50
```

### Rollback Bad Deployment
```bash
kubectl rollout undo deployment/django-app-ssc -n tenant-ssc
kubectl rollout undo deployment/django-app-masa -n tenant-masa
```

---

## 🔓 Add Your Puerto Rico IP to Firewall

### From Browser Console → Cloud Shell:
```bash
# Download, review, then run:
curl -s -o emergency-ssh-access.sh https://raw.githubusercontent.com/pietbarber/Manage2Soar/main/emergency-ssh-access.sh
less emergency-ssh-access.sh   # review before executing
bash emergency-ssh-access.sh
```

### Or Manually:
```bash
MY_IP=$(curl -s ifconfig.me)

# First, get the current source ranges:
EXISTING=$(gcloud compute firewall-rules describe m2s-database-allow-ssh \
  --project=manage2soar --format='get(sourceRanges)' | tr ';' ',')

# Then update, appending your IP:
gcloud compute firewall-rules update m2s-database-allow-ssh \
  --source-ranges="${EXISTING},${MY_IP}/32" \
  --project=manage2soar
```

---

## 📊 Database Issues

**SSH to database (Cloud Shell):**
```bash
gcloud compute ssh pb@m2s-database --zone=us-east1-b --project=manage2soar
```

**Then run:**
```bash
sudo systemctl status postgresql
df -h  # Check disk space
sudo -u postgres psql -c "SELECT count(*) FROM pg_stat_activity;"
```

---

## 📱 Bookmarks for Phone

- GCP Console: https://console.cloud.google.com/?project=manage2soar
- Cloud Shell: https://shell.cloud.google.com
- GKE Cluster: https://console.cloud.google.com/kubernetes/workloads?project=manage2soar
- Logs: https://console.cloud.google.com/logs?project=manage2soar

---

## 🏠 When Home: Remove Puerto Rico IP
```bash
# Get current ranges, then remove the Puerto Rico IP manually:
gcloud compute firewall-rules describe m2s-database-allow-ssh \
  --project=manage2soar --format='get(sourceRanges)'

# Update with the ranges MINUS your travel IP:
gcloud compute firewall-rules update m2s-database-allow-ssh \
  --source-ranges="<PASTE_RANGES_WITHOUT_TRAVEL_IP>" \
  --project=manage2soar
```

---

**Full docs:** `/docs/runbooks/emergency-puerto-rico-access.md`
