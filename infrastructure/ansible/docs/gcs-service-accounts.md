# GCS Service Account Reference

## Production Service Account (ACTIVE)

**File:** `manage2soar-django-key.json` (project root)  
**Service Account:** `manage2soar-django@manage2soar.iam.gserviceaccount.com`  
**GCP Project:** `manage2soar`  
**Bucket:** `gs://manage2soar`  
**Permissions:** `roles/storage.objectAdmin`  
**Usage:** Production deployments for SSC and MASA tenants  
**Created:** 2026-01-08  

### When to Use
- ✅ All production GKE deployments
- ✅ Kubernetes secret `gcp-sa-key` in tenant namespaces
- ✅ Ansible playbook `gke-deploy.yml` (configured in `gcp_app/vars.yml`)
- ✅ Environment variable: `GOOGLE_APPLICATION_CREDENTIALS=/var/secrets/google/key.json`

### Verification
```bash
# Check service account identity in key file
python3 -c "import json; key = json.load(open('manage2soar-django-key.json')); print(key['client_email'])"

# Expected output:
# manage2soar-django@manage2soar.iam.gserviceaccount.com
```

---

## Legacy Service Account (DO NOT USE)

**File:** `skyline-soaring-storage.json` (project root)  
**Service Account:** `django@skyline-soaring-storage.iam.gserviceaccount.com`  
**GCP Project:** `skyline-soaring-storage` (old project)  
**Status:** ⚠️ **DEPRECATED - Do not use for production**  

### Why Not to Use
- ❌ Wrong GCP project (skyline-soaring-storage ≠ manage2soar)
- ❌ No permissions on production `gs://manage2soar` bucket
- ❌ Legacy project that is not used for current deployment

### When It Might Be Used
- Local development testing (if pointing to old storage bucket)
- Historical reference only
- Keep file for archival purposes but DO NOT configure in production

---

## Troubleshooting

### CMS Image Upload Fails (403 Error)
Check which service account is configured:
```bash
kubectl exec -n tenant-ssc deployment/django-app-ssc -- \
  python -c "import json; print(json.load(open('/var/secrets/google/key.json'))['client_email'])"
```

**Expected:** `manage2soar-django@manage2soar.iam.gserviceaccount.com`  
**Wrong:** `django@skyline-soaring-storage.iam.gserviceaccount.com` (means wrong key is deployed)

### Re-create Service Account Key (if compromised)
```bash
# Delete old key (get key ID from GCP Console or list keys)
gcloud iam service-accounts keys delete [KEY_ID] \
  --iam-account=manage2soar-django@manage2soar.iam.gserviceaccount.com \
  --project=manage2soar

# Create new key
gcloud iam service-accounts keys create manage2soar-django-key.json \
  --iam-account=manage2soar-django@manage2soar.iam.gserviceaccount.com \
  --project=manage2soar

# Update Kubernetes secret
kubectl delete secret gcp-sa-key -n tenant-ssc
kubectl create secret generic gcp-sa-key -n tenant-ssc \
  --from-file=key.json=manage2soar-django-key.json

# Restart pods to pick up new secret
kubectl rollout restart deployment/django-app-ssc -n tenant-ssc
```

---

## IaC Integration

The correct service account key is configured in:
- **Ansible vars:** `infrastructure/ansible/group_vars/gcp_app/vars.yml`
- **Variable:** `gke_gcp_sa_key_file`
- **Deployment role:** `infrastructure/ansible/roles/gke-deploy/`

When running `ansible-playbook playbooks/gke-deploy.yml`, the role will:
1. Read `manage2soar-django-key.json` from project root
2. Create Kubernetes secret `gcp-sa-key` in each tenant namespace
3. Mount secret to `/var/secrets/google/key.json` in pods
4. Set `GOOGLE_APPLICATION_CREDENTIALS` environment variable

This is the IaC-first approach - always update the Ansible configuration and re-run the playbook rather than manually patching Kubernetes resources.
