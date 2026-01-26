# manage2soar/storage_backends.py

from django.conf import settings
from django.contrib.staticfiles.storage import ManifestFilesMixin
from storages.backends.gcloud import GoogleCloudStorage


class MediaRootGCS(GoogleCloudStorage):
    # Use your single bucket; keep media under a "media/" prefix
    # Note: bucket_name can be None for local dev; this backend is only used when GCS is configured
    bucket_name = getattr(settings, "GS_BUCKET_NAME", None)
    location = getattr(settings, "GS_MEDIA_LOCATION", "media")
    file_overwrite = False
    default_acl = None  # Use None with uniform bucket-level access
    # Custom querystring auth to force unsigned URLs for public buckets
    querystring_auth = False  # Generate unsigned URLs instead of signed URLs
    object_parameters = {"cache_control": "public, max-age=3600"}


class StaticRootGCS(GoogleCloudStorage):
    # Note: bucket_name can be None for local dev; this backend is only used when GCS is configured
    bucket_name = getattr(settings, "GS_BUCKET_NAME", None)
    location = getattr(settings, "GS_STATIC_LOCATION", "static")
    default_acl = None  # Use None with uniform bucket-level access
    # Custom querystring auth to force unsigned URLs for public buckets
    querystring_auth = False  # Generate unsigned URLs instead of signed URLs
    file_overwrite = True
    # Skip ManifestFilesMixin to avoid post-processing issues on GCP
    # Issue #567: Add CORS headers to fix CORB blocking of CSS/JS files
    object_parameters = {
        "cache_control": "public, max-age=31536000, immutable",
        "content_disposition": "inline",  # Serve files inline, not as downloads
    }
