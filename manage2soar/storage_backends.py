# manage2soar/storage_backends.py

from django.conf import settings
from django.contrib.staticfiles.storage import ManifestFilesMixin
from storages.backends.gcloud import GoogleCloudStorage


class MediaRootGCS(GoogleCloudStorage):
    # Use your single bucket; keep media under a "media/" prefix
    bucket_name = settings.GS_BUCKET_NAME
    location = getattr(settings, "GS_MEDIA_LOCATION", "media")
    file_overwrite = False
    default_acl = None  # Use None with uniform bucket-level access
    # Custom querystring auth to force unsigned URLs for public buckets
    querystring_auth = False  # Generate unsigned URLs instead of signed URLs
    object_parameters = {"cache_control": "public, max-age=3600"}


class StaticRootGCS(GoogleCloudStorage):
    bucket_name = settings.GS_BUCKET_NAME
    location = getattr(settings, "GS_STATIC_LOCATION", "static")
    default_acl = None  # Use None with uniform bucket-level access
    # Custom querystring auth to force unsigned URLs for public buckets
    querystring_auth = False  # Generate unsigned URLs instead of signed URLs
    file_overwrite = True
    # Skip ManifestFilesMixin to avoid post-processing issues on GCP
    object_parameters = {"cache_control": "public, max-age=31536000, immutable"}
