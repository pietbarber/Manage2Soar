# TinyMCE Signed URLs Fix - Issue Resolution

## Problem
TinyMCE image uploads were generating temporary Google Cloud Storage signed URLs instead of permanent URLs. These signed URLs contain authentication tokens like `?X-Goog-Algorithm=GOOG4-RSA-SHA256&X-Goog-Credential=...` that expire after a certain time, creating a "ticking time bomb" where images would become inaccessible.

## Root Cause
The issue was in the Google Cloud Storage configuration in `manage2soar/storage_backends.py`. When using uniform bucket-level access (which is the security best practice), individual object ACLs cannot be set. The storage backend was falling back to generating signed URLs instead of public URLs.

## Solution Applied

### 1. Fixed Storage Backend Configuration
Updated `manage2soar/storage_backends.py` to set `querystring_auth = False`:

```python
class MediaRootGCS(GoogleCloudStorage):
    bucket_name = settings.GS_BUCKET_NAME
    location = getattr(settings, "GS_MEDIA_LOCATION", "media")
    file_overwrite = False
    default_acl = None  # Use None with uniform bucket-level access
    querystring_auth = False  # Generate unsigned URLs instead of signed URLs
    object_parameters = {"cache_control": "public, max-age=3600"}

class StaticRootGCS(GoogleCloudStorage):
    bucket_name = settings.GS_BUCKET_NAME
    location = getattr(settings, "GS_STATIC_LOCATION", "static")
    default_acl = None  # Use None with uniform bucket-level access
    querystring_auth = False  # Generate unsigned URLs instead of signed URLs
    file_overwrite = True
    object_parameters = {"cache_control": "public, max-age=31536000, immutable"}
```

### 2. Cleaned Up Existing Signed URLs
Identified and fixed 3 existing signed URLs in the database:
- 2 URLs in `logsheet_logsheetcloseout.equipment_issues` (ID: 11)
- 1 URL in `instructors_syllabusdocument.content` (ID: 1)

## Files Modified
1. `/home/pb/Projects/skylinesoaring/manage2soar/storage_backends.py` - Added `querystring_auth = False`
2. Database records cleaned up via Django shell commands

## Verification
- ✅ No signed URLs remain in HTMLField entries
- ✅ New TinyMCE uploads generate permanent URLs
- ✅ URLs follow correct format: `https://storage.googleapis.com/skyline-soaring-storage/ssc/media/tinymce/filename.jpg`

## Monitoring
Created `monitor_signed_urls.sh` script to check for this issue in the future. Run periodically to ensure no signed URLs creep back in.

## Technical Details

### Why This Happened
- Google Cloud Storage with uniform bucket-level access enabled
- `default_acl = None` with `querystring_auth = True` (default) generates signed URLs
- Setting `querystring_auth = False` forces unsigned public URLs

### Why This Solution Works
- Uniform bucket-level access ensures security through IAM
- `querystring_auth = False` tells django-storages to generate simple public URLs
- No authentication tokens means URLs never expire
- Bucket-level public read access allows the URLs to work

## Prevention
- Monitor using the `monitor_signed_urls.sh` script
- Ensure any future storage backend changes maintain `querystring_auth = False`
- Test TinyMCE uploads after any django-storages or GCS configuration changes

## Impact
- Fixed immediate problem of expiring image URLs
- Prevented future "broken images" issues
- Maintained security through proper bucket-level IAM permissions
- All TinyMCE image uploads now generate permanent, reliable URLs
