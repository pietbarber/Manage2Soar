# manage2soar/storage_backends.py
import os

from django.conf import settings
from django.contrib.staticfiles.storage import ManifestFilesMixin
from storages.backends.gcloud import GoogleCloudStorage


class MediaRootGCS(GoogleCloudStorage):
    # Use your single bucket; keep media under a "media/" prefix
    bucket_name = settings.GS_BUCKET_NAME
    location = getattr(settings, "GS_MEDIA_LOCATION", "media")
    file_overwrite = False
    default_acl = None  # with Uniform bucket-level access, manage via IAM
    object_parameters = {"cache_control": "public, max-age=3600"}


class StaticRootGCS(ManifestFilesMixin, GoogleCloudStorage):
    bucket_name = settings.GS_BUCKET_NAME
    location = getattr(settings, "GS_STATIC_LOCATION", "static")
    default_acl = None
    file_overwrite = True
    object_parameters = {"cache_control": "public, max-age=31536000, immutable"}
