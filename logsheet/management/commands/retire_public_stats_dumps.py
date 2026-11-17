"""Inventory, then explicitly retire this tenant's legacy public stats exports."""

import json
from pathlib import PurePosixPath

from django.conf import settings
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from logsheet.models import StatsDumpOutbox
from logsheet.stats_storage import LEGACY_STATS_PREFIX


def legacy_names(directory=LEGACY_STATS_PREFIX.rstrip("/")):
    try:
        directories, files = default_storage.listdir(directory)
    except FileNotFoundError:
        return
    for filename in files:
        yield f"{directory}/{filename}"
    for child in directories:
        yield from legacy_names(f"{directory}/{child}")


class Command(BaseCommand):
    help = "Inventory public stats dumps (JSON); --apply permanently retires them. Stop export workers first."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        # The deployment is one DB/settings environment per tenant. Never loop
        # over another tenant's bucket prefix or accept arbitrary object paths.
        jobs = StatsDumpOutbox.objects.filter(
            result_file__startswith=LEGACY_STATS_PREFIX
        )
        rows = list(jobs.values("id", "status", "result_file"))
        names = sorted(set(legacy_names()) | {row["result_file"] for row in rows})
        for name in names:
            if (
                not name.startswith(LEGACY_STATS_PREFIX)
                or any(part in (".", "..") for part in name.split("/"))
                or "\\" in name
                or PurePosixPath(name).is_absolute()
            ):
                raise CommandError(
                    "Unsafe legacy object name; inspect inventory manually."
                )
        self.stdout.write(
            json.dumps(
                {
                    "tenant": settings.CLUB_PREFIX,
                    "jobs": rows,
                    "objects": names,
                    "apply": options["apply"],
                },
                indent=2,
            )
        )
        if not options["apply"]:
            return
        if StatsDumpOutbox.objects.filter(
            status=StatsDumpOutbox.STATUS_PROCESSING
        ).exists():
            raise CommandError(
                "Stop and drain export workers before retiring public exports."
            )

        # Delete first. If storage deletion fails, keep DB references for retry.
        # If the DB update fails, rerunning is safe (missing files are accepted).
        for name in names:
            with transaction.atomic():
                matching = StatsDumpOutbox.objects.select_for_update().filter(
                    result_file=name
                )
                list(matching.values_list("pk", flat=True))
                default_storage.delete(name)
                if default_storage.exists(name):
                    raise CommandError(
                        f"Public object still exists after deletion: {name}"
                    )
                matching.update(
                    status=StatsDumpOutbox.STATUS_EXPIRED,
                    result_file="",
                    result_filename="",
                    last_error="Public export retired; queue a new private export.",
                )
        self.stderr.write(self.style.SUCCESS("Legacy public stats exports retired."))
