from django.db import transaction
from django.utils import timezone

from logsheet.models import StatsDumpOutbox
from logsheet.stats_storage import STATS_DUMP_RETENTION, private_stats_name


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
            job.result_file.delete(save=False)
            job.status = StatsDumpOutbox.STATUS_EXPIRED
            job.result_filename = ""
            job.save(update_fields=["result_file", "result_filename", "status"])
