"""Private, tenant-scoped stats exports. Never use the public media backend."""

import re
from datetime import timedelta
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, SuspiciousFileOperation
from django.core.files.storage import Storage, storages
from django.utils import timezone
from django.utils.deconstruct import deconstructible

STATS_DUMP_RETENTION = timedelta(days=7)
LEGACY_STATS_PREFIX = "exports/stats_dumps/"


def stats_tenant_prefix():
    prefix = getattr(settings, "CLUB_PREFIX", "")
    if not re.fullmatch(r"[a-zA-Z0-9-]+", prefix):
        raise ImproperlyConfigured("A valid CLUB_PREFIX is required for stats exports.")
    return prefix


def private_stats_name(name):
    return bool(
        re.fullmatch(
            rf"{re.escape(stats_tenant_prefix())}/[0-9a-f]{{32}}(?:_[a-zA-Z0-9]{{7}})?\.csv",
            name,
        )
    )


def stats_dump_upload_to(instance, filename):
    return f"{stats_tenant_prefix()}/{uuid4().hex}.csv"


def stats_dump_expired(job):
    return (
        not job.completed_at
        or job.completed_at <= timezone.now() - STATS_DUMP_RETENTION
    )


@deconstructible
class StatsDumpStorage(Storage):
    """Resolve lazily so missing configuration fails the job, not Django startup.

    Validate on reads AND writes: even a copied foreign tenant DB reference may
    not be opened by this tenant. No URL API, including signed bearer URLs.
    """

    def _backend(self, name):
        if not private_stats_name(name):
            raise SuspiciousFileOperation("Invalid tenant stats export name.")
        return storages["stats_dumps"]

    def _open(self, name, mode="rb"):
        return self._backend(name).open(name, mode)

    def _save(self, name, content):
        return self._backend(name).save(name, content)

    def exists(self, name):
        return self._backend(name).exists(name)

    def delete(self, name):
        return self._backend(name).delete(name)

    def size(self, name):
        return self._backend(name).size(name)

    def url(self, name):
        raise NotImplementedError(
            "Stats exports require the authenticated download view."
        )
