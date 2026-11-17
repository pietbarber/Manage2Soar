import logging

from django.db import transaction
from django.utils import timezone

from logsheet.models import StatsDumpOutbox
from logsheet.stats_storage import STATS_DUMP_RETENTION, private_stats_name

logger = logging.getLogger(__name__)


def expire_stats_dump_exports():
    """Remove expired private files on every worker run, including local storage."""
    ids = StatsDumpOutbox.objects.filter(
        status=StatsDumpOutbox.STATUS_READY,
        completed_at__lte=timezone.now() - STATS_DUMP_RETENTION,
    ).values_list("pk", flat=True)
    for pk in ids.iterator():
        with transaction.atomic():
            job = StatsDumpOutbox.objects.select_for_update().get(pk=pk)
            if job.status != StatsDumpOutbox.STATUS_READY:
                continue
            # Legacy public exports must be explicitly inventoried and retired;
            # never erase the DB reference while leaving the public copy behind.
            if not job.result_file or not private_stats_name(job.result_file.name):
                continue
            try:
                job.result_file.delete(save=False)
            except Exception:
                # Preserve the reference so this object can be retried on the
                # next worker run, while allowing other expirations and queued
                # exports to continue.
                logger.exception(
                    "Could not delete expired stats export for job %s; will retry",
                    job.pk,
                )
                continue
            job.status = StatsDumpOutbox.STATUS_EXPIRED
            job.result_filename = ""
            job.save(update_fields=["result_file", "result_filename", "status"])
