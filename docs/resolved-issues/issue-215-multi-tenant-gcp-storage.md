# Issue #215: Multi-Tenant GCP Storage Architecture

**Issue**: [#215 - Move static content to GCP or NGINX](https://github.com/pietbarber/Manage2Soar/issues/215)  
**Pull Request**: [#226 - Move static content to GCP or NGINX](https://github.com/pietbarber/Manage2Soar/pull/226)  
**Resolution Date**: November 6, 2025  
**Status**: ✅ **RESOLVED**

## Problem Statement

The original implementation used WhiteNoise for serving static files directly from Django pods in Kubernetes. This approach had several limitations:

### Technical Issues
- **Performance**: Static files served through Django application pods
- **Resource Usage**: Increased memory footprint in Kubernetes containers
- **Scalability**: Not optimized for CDN delivery or multi-region deployments
- **Architecture**: Mixed static content serving with application logic

### Business Requirements
- **Multi-tenant Architecture**: Need to support multiple flying clubs with isolated data
- **Shared Infrastructure**: Clubs should share the same codebase and infrastructure
- **Cost Efficiency**: Avoid duplicating storage and management overhead
- **Scalability**: Easy to onboard new clubs without infrastructure changes

## Solution Architecture

### Multi-Tenant Storage Structure

```
Google Cloud Storage Bucket: skyline-soaring-storage/
├── ssc/                    # Skyline Soaring Club
│   ├── static/            # CSS, JS, images, admin files
│   └── media/             # User uploads, avatars, documents
├── masa/                   # Mid-Atlantic Soaring Association  
│   ├── static/
│   └── media/
└── nfss/                   # Northern Florida Soaring Society
    ├── static/
    └── media/
```

### Key Design Principles

1. **Isolation**: Each club's data is completely separated by path prefixes
2. **Shared Resources**: Single bucket reduces costs and management overhead
3. **Scalability**: Adding new clubs requires only environment configuration
4. **Security**: Path-based isolation prevents cross-club data access

## Implementation Details

### Django Configuration Changes

#### Settings Architecture
```python
# Multi-tenant support: Club-specific storage paths
CLUB_PREFIX = os.getenv("CLUB_PREFIX", "ssc")  # Default to Skyline Soaring Club

# Validate CLUB_PREFIX to prevent path traversal attacks
import re
if not re.match(r'^[a-zA-Z0-9-]+$', CLUB_PREFIX):
    raise Exception(f"Invalid CLUB_PREFIX '{CLUB_PREFIX}'. Must contain only alphanumeric characters and hyphens.")

# Dynamic path generation
GS_MEDIA_LOCATION = os.getenv("GS_MEDIA_LOCATION", f"{CLUB_PREFIX}/media")
GS_STATIC_LOCATION = os.getenv("GS_STATIC_LOCATION", f"{CLUB_PREFIX}/static")

# Multi-tenant GCP URLs
STATIC_URL = os.getenv(
    "STATIC_URL",
    f"https://storage.googleapis.com/{GS_BUCKET_NAME}/{GS_STATIC_LOCATION}/",
)
```

#### Storage Backend Configuration
```python
STORAGES = {
    "default": {
        "BACKEND": "manage2soar.storage_backends.MediaRootGCS",
    },
    "staticfiles": {
        "BACKEND": "manage2soar.storage_backends.StaticRootGCS",
    },
}
```

### Security Enhancements

#### Input Validation
- **CLUB_PREFIX Validation**: Regex validation prevents path traversal attacks (`../other-club`)
- **GS_BUCKET_NAME Validation**: Startup fails if critical GCP configuration is missing
- **URL Generation Protection**: Early validation prevents malformed URLs

#### Path Traversal Prevention
```python
# Blocks malicious values like: "../other-club", "../../sensitive", etc.
if not re.match(r'^[a-zA-Z0-9-]+$', CLUB_PREFIX):
    raise Exception("Invalid CLUB_PREFIX - prevents path traversal security issues")
```

### Database Content Migration

#### TinyMCE URL Updates
A critical discovery was that existing TinyMCE rich text content contained hardcoded media URLs that needed updating:

- **Models Affected**: Member biographies, CMS pages, instruction content
- **Pattern**: `https://storage.googleapis.com/bucket/media/` → `https://storage.googleapis.com/bucket/ssc/media/`
- **Solution**: Django management command with safe pattern replacement
- **Result**: 4 media URLs successfully updated across the site

## Deployment Architecture

### Environment Configuration

Each club deployment uses environment variables for isolation:

```bash
# Skyline Soaring Club
CLUB_PREFIX=ssc
GS_MEDIA_LOCATION=ssc/media
GS_STATIC_LOCATION=ssc/static
STATIC_URL=https://storage.googleapis.com/bucket-name/ssc/static/

# Mid-Atlantic Soaring Association  
CLUB_PREFIX=masa
GS_MEDIA_LOCATION=masa/media
GS_STATIC_LOCATION=masa/static
STATIC_URL=https://storage.googleapis.com/bucket-name/masa/static/
```

### Kubernetes Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: manage2soar-ssc
spec:
  containers:
  - name: manage2soar
    env:
    - name: CLUB_PREFIX
      value: "ssc"
    - name: GS_BUCKET_NAME
      value: "shared-storage-bucket"
    # Additional environment variables...
```

### DNS and Domain Mapping

```
ssc.manage2soar.com  → Skyline Soaring Club (CLUB_PREFIX=ssc)
masa.manage2soar.com → Mid-Atlantic SA (CLUB_PREFIX=masa)  
nfss.manage2soar.com → Northern Florida SS (CLUB_PREFIX=nfss)
```

## Performance Considerations

### Build Time Trade-offs

**Challenge**: `collectstatic` now uploads to GCP during Docker builds, increasing build time from ~19 seconds to ~137 seconds.

**Decision**: Accepted the trade-off for deployment reliability:
- ✅ **Clean deployments** - No stale static files
- ✅ **Build-time validation** - Immediate feedback on static file issues  
- ✅ **Consistent state** - Every deployment starts fresh
- ✅ **Simple architecture** - No complex versioning needed

**Alternative Approaches Considered**:
1. **Versioned static paths** - Each deployment gets unique path
2. **Init containers** - Separate static file deployment phase
3. **Multi-stage builds** - Build and runtime separation
4. **Build caching** - CI/CD-level static file caching

**Conclusion**: The straightforward approach of "build clean, deploy clean" provides the best balance of reliability and simplicity for current deployment frequency.

## Benefits Achieved

### Technical Benefits
- ✅ **Performance**: Static files served directly from GCP with CDN capabilities
- ✅ **Scalability**: Supports unlimited clubs with isolated storage
- ✅ **Resource Efficiency**: Reduced Django pod memory usage
- ✅ **Architecture**: Clean separation of concerns

### Business Benefits  
- ✅ **Multi-club Ready**: Foundation for SaaS expansion
- ✅ **Cost Efficiency**: Shared infrastructure with isolated data
- ✅ **Operational**: Single bucket to manage vs. multiple storage systems
- ✅ **Security**: Complete data isolation between clubs

### Development Benefits
- ✅ **Environment Parity**: Same storage patterns in dev/staging/prod
- ✅ **Testing**: Easy to test multi-tenant scenarios locally
- ✅ **Debugging**: Clear path structure makes troubleshooting easier
- ✅ **Documentation**: Well-documented patterns for future clubs

## Lessons Learned

### Code Review Value
GitHub Copilot's automated review identified 10 critical issues including:
- Missing input validation for security
- Documentation inconsistencies  
- Code quality improvements
- PEP 8 compliance issues

**Outcome**: All critical security and configuration issues were resolved, demonstrating the value of automated code review for infrastructure changes.

### Database Content Dependencies
**Discovery**: Moving media files doesn't automatically update database content references.

**Learning**: Always audit rich text content (TinyMCE, CKEditor, etc.) when migrating file storage locations.

**Solution**: Created reusable Django management command pattern for content URL migrations.

### Documentation Strategy
**Observation**: `.env` file examples using `${VARIABLE}` syntax confused users since `.env` files don't support variable substitution by default.

**Resolution**: Use literal values in documentation examples with clear notes about variable substitution limitations.

## Future Enhancements

### Potential Optimizations
1. **CDN Integration**: Add CloudFlare or GCP CDN for global performance
2. **Multi-region**: Deploy clubs in their geographic regions
3. **Advanced Monitoring**: Per-club metrics and alerting
4. **Automated Backups**: Club-specific backup schedules

### Scaling Considerations
1. **Storage Costs**: Monitor per-club usage patterns
2. **Access Patterns**: Optimize for club-specific traffic patterns  
3. **Geographic Distribution**: Consider regional storage for international clubs
4. **Compliance**: Address data residency requirements per jurisdiction

## Related Documentation

- [Multi-Tenant Deployment Guide](../multi-tenant-deployment.md)
- [Issue #215 Implementation Summary](../issue-215-implementation-summary.md)
- [Storage Backend Configuration](../../manage2soar/storage_backends.py)
- [CronJob Architecture](../cronjob-architecture.md)

## Migration Guide

For clubs wanting to adopt this architecture:

1. **Environment Setup**: Configure `CLUB_PREFIX` and GCP storage variables
2. **Database Migration**: Run content URL update command if migrating existing data
3. **Static Files**: Run `collectstatic` to populate club-specific storage
4. **DNS Configuration**: Set up club-specific subdomain
5. **Testing**: Verify static files and media uploads work correctly

This multi-tenant architecture provides a solid foundation for growing Manage2Soar into a platform that can serve multiple flying clubs while maintaining complete data isolation and cost efficiency.