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