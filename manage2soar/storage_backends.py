# manage2soar/storage_backends.py

import os
import tempfile
from pathlib import Path

from django.conf import settings
from django.contrib.staticfiles.storage import ManifestFilesMixin
from django.core.exceptions import ImproperlyConfigured
from django.core.files.storage import FileSystemStorage
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


class PrivateImportExportGCS(GoogleCloudStorage):
    location = "django-import-export"
    default_acl = None
    querystring_auth = True
    file_overwrite = False

    def __init__(self, *args, **kwargs):
        bucket_name = getattr(settings, "GS_IMPORT_EXPORT_BUCKET_NAME", None)
        if not bucket_name:
            raise ImproperlyConfigured(
                "GS_IMPORT_EXPORT_BUCKET_NAME must be set for private import/export storage."
            )
        super().__init__(*args, **kwargs)
        self.bucket_name = bucket_name


class PrivateStatsDumpGCS(GoogleCloudStorage):
    """Reuse the private bucket, outside the one-day import staging prefix."""

    def __init__(self, **kwargs):
        bucket = getattr(settings, "GS_IMPORT_EXPORT_BUCKET_NAME", None)
        if not bucket or bucket == getattr(settings, "GS_BUCKET_NAME", None):
            raise ImproperlyConfigured(
                "Stats exports require GS_IMPORT_EXPORT_BUCKET_NAME distinct from public media."
            )
        kwargs.update(
            bucket_name=bucket,
            location="stats-dumps",
            default_acl=None,
            querystring_auth=True,
            file_overwrite=False,
            object_parameters={"cache_control": "private, no-store, max-age=0"},
        )
        super().__init__(**kwargs)

    def url(self, name, **kwargs):
        raise NotImplementedError(
            "Stats exports require the authenticated download view."
        )


class PrivateStatsDumpFileSystemStorage(FileSystemStorage):
    def __init__(self, **kwargs):
        root = getattr(settings, "STATS_DUMP_ROOT", None)
        if not root:
            if not settings.DEBUG:
                raise ImproperlyConfigured(
                    "STATS_DUMP_ROOT is required outside development."
                )
            user_id = os.getuid() if hasattr(os, "getuid") else "dev"
            root = Path(tempfile.gettempdir()) / f"m2s-stats-dumps-{user_id}"
        root = Path(root).resolve()
        # Reject both a served directory and its ancestor, including symlinks.
        for setting in ("MEDIA_ROOT", "STATIC_ROOT", "BASE_DIR"):
            served = getattr(settings, setting, None)
            if served:
                served = Path(served).resolve()
                if root.is_relative_to(served) or served.is_relative_to(root):
                    raise ImproperlyConfigured(
                        f"STATS_DUMP_ROOT must be separate from {setting}."
                    )
        kwargs.update(
            location=root,
            base_url=None,
            file_permissions_mode=0o600,
            directory_permissions_mode=0o700,
        )
        super().__init__(**kwargs)

    def url(self, name):
        raise NotImplementedError(
            "Stats exports require the authenticated download view."
        )
