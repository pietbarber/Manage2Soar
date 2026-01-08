# Multi-Tenant Deployment Guide

## Overview

Manage2Soar supports multiple flying clubs using a shared GCP bucket with isolated directories. Each club gets their own subdomain and storage path while sharing the same codebase and infrastructure.

## Architecture

```
GCP Bucket: {GS_BUCKET_NAME}/
├── ssc/                    # Skyline Soaring Club
│   ├── static/            # Static files (CSS, JS, images)
│   └── media/             # User uploads (avatars, documents)
├── masa/                   # Mid-Atlantic Soaring Association  
│   ├── static/
│   └── media/
└── nfss/                   # Northern Florida Soaring Society
    ├── static/
    └── media/
```

## Domain Mapping

| Club | Domain | CLUB_PREFIX |
|------|--------|-------------|
| Skyline Soaring Club | ssc.manage2soar.com | `ssc` |
| Mid-Atlantic Soaring Association | masa.manage2soar.com | `masa` |
| Northern Florida Soaring Society | nfss.manage2soar.com | `nfss` |

## Google OAuth2 Configuration (Per-Tenant)

### Overview

Each tenant requires its own Google OAuth2 credentials to ensure proper security isolation and tenant-specific branding. This prevents cross-tenant authentication issues and allows independent credential management.

### Setup Steps for Each Tenant

#### 1. Create OAuth2 Credentials in Google Cloud Console

For each tenant, create separate OAuth2 credentials:

1. **Go to Google Cloud Console**: https://console.cloud.google.com/
2. **Select or create a project** for the tenant (e.g., "Manage2Soar-SSC")
3. **Navigate to**: APIs & Services → Credentials
4. **Configure OAuth Consent Screen**:
   - User Type: Choose **External** (public) or **Internal** (G Suite only)
   - App name: Use tenant-specific name (e.g., "Skyline Soaring Club Portal")
   - Support email: Tenant contact email
   - Application logo: Tenant logo (optional)
   - Authorized domains: Add `manage2soar.com`
   - Scopes: Add `openid`, `email`, `profile`
   - Test users: Add test accounts if in testing phase

5. **Create OAuth Client ID**:
   - Click "Create Credentials" → "OAuth client ID"
   - Application type: **Web application**
   - Name: `Manage2Soar - [Tenant Name]`
   - Authorized redirect URIs:
     - Production: `https://[tenant].manage2soar.com/complete/google-oauth2/`
     - Development: `http://127.0.0.1:8001/complete/google-oauth2/` (optional)
   - Authorized JavaScript origins:
     - Production: `https://[tenant].manage2soar.com`
     - Development: `http://127.0.0.1:8001` (optional)

6. **Download credentials**: Save Client ID and Client Secret

#### 2. Store Credentials in Ansible Vault

Edit your encrypted vault file:

```bash
cd infrastructure/ansible
ansible-vault edit group_vars/gcp_app/vault.yml --vault-password-file ~/.ansible_vault_pass
```

Add per-tenant OAuth2 credentials:

```yaml
# SSC (Skyline Soaring Club)
vault_google_oauth_client_id_ssc: "123456789-abc.apps.googleusercontent.com"
vault_google_oauth_client_secret_ssc: "GOCSPX-your-secret-here"

# MASA (Mid-Atlantic Soaring Association)
vault_google_oauth_client_id_masa: "987654321-xyz.apps.googleusercontent.com"
vault_google_oauth_client_secret_masa: "GOCSPX-another-secret-here"

# NFSS (Northern Florida Soaring Society)
vault_google_oauth_client_id_nfss: "555555555-nfss.apps.googleusercontent.com"
vault_google_oauth_client_secret_nfss: "GOCSPX-nfss-secret-here"
```

**Variable naming convention**: `vault_google_oauth_client_id_[CLUB_PREFIX]`

#### 3. Deploy

The Ansible playbooks will automatically inject the correct OAuth2 credentials for each tenant based on their `CLUB_PREFIX`:

```bash
cd infrastructure/ansible
ansible-playbook -i inventory.yml playbooks/gke-deploy.yml -e "gke_club_prefix=ssc"
ansible-playbook -i inventory.yml playbooks/gke-deploy.yml -e "gke_club_prefix=masa"
ansible-playbook -i inventory.yml playbooks/gke-deploy.yml -e "gke_club_prefix=nfss"
```

### Security Benefits

- **Isolation**: Each tenant has completely separate OAuth2 credentials
- **Branding**: Each tenant's consent screen shows tenant-specific information
- **Revocation**: Credentials can be revoked per-tenant without affecting others
- **Audit**: OAuth2 usage tracking is tenant-specific in Google Cloud Console
- **Risk mitigation**: Credential compromise only affects one tenant

### Testing

After deployment, test OAuth2 login for each tenant:

1. Navigate to tenant domain: `https://ssc.manage2soar.com`
2. Click "Sign in with Google"
3. Verify consent screen shows correct tenant name
4. Complete authentication
5. Verify login succeeds and user is directed to member homepage

### Troubleshooting

**Redirect URI mismatch error**:
- Ensure the redirect URI in Google Cloud Console exactly matches the tenant domain
- Check for trailing slashes: `/complete/google-oauth2/` (with slash)
- Verify HTTPS is used in production (not HTTP)

**Credentials not found**:
- Verify vault variable naming: `vault_google_oauth_client_id_[CLUB_PREFIX]`
- Check that `CLUB_PREFIX` matches exactly (case-sensitive)
- Confirm vault.yml is properly decrypted during deployment

**Cross-tenant login issues**:
- Each tenant must use only their own OAuth2 credentials
- Never share credentials between tenants
- Verify each tenant's Kubernetes Secret contains correct credentials



## Environment Configuration

### Skyline Soaring Club (.env)

> **Note:** `.env` files do **not** support variable substitution (e.g., `${CLUB_PREFIX}`) by default. You must use literal values, or preprocess with a tool like `envsubst`. The example below uses literal values for clarity.

```bash
# Club Configuration
CLUB_PREFIX=ssc

# Google Cloud Storage
GS_BUCKET_NAME=your-bucket-name
GS_MEDIA_LOCATION=ssc/media
GS_STATIC_LOCATION=ssc/static
STATIC_URL=https://storage.googleapis.com/your-bucket-name/ssc/static/

# Database
DATABASE_URL=postgresql://user:pass@host:port/ssc_manage2soar

# Other settings...
```

### Mid-Atlantic Soaring Association (.env)
```bash  
# Club Configuration
CLUB_PREFIX=masa

# Google Cloud Storage
GS_BUCKET_NAME=your-bucket-name
GS_MEDIA_LOCATION=masa/media
GS_STATIC_LOCATION=masa/static
STATIC_URL=https://storage.googleapis.com/your-bucket-name/masa/static/

# Database
DATABASE_URL=postgresql://user:pass@host:port/masa_manage2soar

# Other settings...
```

### Northern Florida Soaring Society (.env)
```bash
# Club Configuration  
CLUB_PREFIX=nfss

# Google Cloud Storage
GS_BUCKET_NAME=your-bucket-name
GS_MEDIA_LOCATION=nfss/media
GS_STATIC_LOCATION=nfss/static
STATIC_URL=https://storage.googleapis.com/your-bucket-name/nfss/static/

# Database
DATABASE_URL=postgresql://user:pass@host:port/nfss_manage2soar

# Other settings...
```

## Deployment Steps

### 1. Initial Setup for New Club

1. **Create Environment File**
   ```bash
   cp .env .env.masa  # or .env.nfss
   # Edit the new file with appropriate CLUB_PREFIX and paths
   ```

2. **Create Separate Database**
   ```bash
   # Create new database for the club
   createdb masa_manage2soar  # or nfss_manage2soar
   ```

3. **Run Migrations**
   ```bash
   # Set environment for new club
   export DJANGO_SETTINGS_MODULE=manage2soar.settings
   # Load new environment
   source .env.masa  # or .env.nfss

   # Run migrations
   python manage.py migrate
   ```

4. **Load Initial Data**
   ```bash
   # Load basic groups and permissions
   python manage.py loaddata loaddata/groups_and_permissions.json

   # Load other fixtures as needed
   python manage.py loaddata loaddata/members.Badge.json
   python manage.py loaddata loaddata/instructors.*.json
   ```

5. **Collect Static Files**
   ```bash
   python manage.py collectstatic --noinput
   ```

6. **Create Superuser**
   ```bash
   python manage.py createsuperuser
   ```

### 2. Kubernetes Deployment

Each club gets its own deployment with environment-specific configuration:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: manage2soar-masa
spec:
  replicas: 2
  selector:
    matchLabels:
      app: manage2soar-masa
  template:
    metadata:
      labels:
        app: manage2soar-masa
    spec:
      containers:
      - name: manage2soar
        image: manage2soar:latest
        env:
        - name: CLUB_PREFIX
          value: "masa"
        - name: GS_MEDIA_LOCATION
          value: "masa/media"
        - name: GS_STATIC_LOCATION
          value: "masa/static"
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: masa-db-secret
              key: url
        # ... other environment variables
```

### 3. DNS and SSL Setup

1. **DNS Records**
   ```
   ssc.manage2soar.com  -> Load Balancer IP
   masa.manage2soar.com -> Load Balancer IP  
   nfss.manage2soar.com -> Load Balancer IP
   ```

2. **SSL Certificates**
   ```yaml
   apiVersion: networking.gke.io/v1
   kind: ManagedCertificate
   metadata:
     name: manage2soar-ssl
   spec:
     domains:
       - ssc.manage2soar.com
       - masa.manage2soar.com
       - nfss.manage2soar.com
   ```

## Storage Benefits

### Shared Infrastructure
- **Single GCP Bucket**: Simplified billing and management using ${GS_BUCKET_NAME}
- **Shared Service Account**: One set of credentials for all clubs
- **Cost Efficiency**: Shared storage pricing tiers

### Isolated Data
- **Separate Directories**: Complete data isolation between clubs
- **Independent Backups**: Can backup each club separately
- **Scalable**: Easy to add new clubs with new prefixes

## Testing Static Files

### Verify Configuration
```python
from django.core.files.storage import storages
static_storage = storages['staticfiles']

# Test a file URL
url = static_storage.url('css/baseline.css')
print(url)
# Should show: https://storage.googleapis.com/{GS_BUCKET_NAME}/{CLUB_PREFIX}/static/css/baseline.css
```

### Check File Access
```bash
# Test if static files are accessible
curl -I https://storage.googleapis.com/${GS_BUCKET_NAME}/ssc/static/css/baseline.css
# Should return 200 OK
```

## Troubleshooting

### Common Issues

1. **Static files not loading**
   - Verify `CLUB_PREFIX` is set correctly
   - Run `python manage.py collectstatic --noinput`
   - Check GCP service account permissions

2. **Cross-club data leakage**
   - Verify each deployment uses correct `CLUB_PREFIX`
   - Check database connections are club-specific
   - Ensure media/static paths don't overlap

3. **Storage permissions**
   - Verify service account has Storage Admin role
   - Check bucket-level IAM permissions
   - Ensure CORS settings allow web access

### Monitoring

- **Storage Usage**: Monitor per-prefix storage usage in GCP Console
- **Access Logs**: Enable GCS access logging for audit trails  
- **Performance**: Monitor static file load times from different regions

## Security Considerations

- Each club should have separate databases
- Service account credentials should be rotated regularly
- Consider bucket-level access controls for sensitive data
- Use signed URLs for private media files
- Enable audit logging for compliance

## Future Enhancements

- **CDN Integration**: Add CloudFlare or GCP CDN for better performance
- **Multi-Region**: Deploy clubs in their geographic regions
- **Advanced Monitoring**: Per-club metrics and alerting
- **Automated Backups**: Club-specific backup schedules
