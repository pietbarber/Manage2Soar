from django.core.management.base import BaseCommand

from duty_roster.models import DutyAssignment


class Command(BaseCommand):
    help = (
        "Backfill normalized DutyAssignmentRole rows from legacy DutyAssignment fields. "
        "Idempotent and safe to run multiple times."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be synced without writing changes.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        assignments = DutyAssignment.objects.all().order_by("date")
        total = assignments.count()
        synced = 0

        self.stdout.write(
            f"Processing {total} duty assignment(s)" + (" [dry-run]" if dry_run else "")
        )

        for assignment in assignments.iterator():
            if dry_run:
                self.stdout.write(
                    f"Would sync assignment {assignment.pk} ({assignment.date.isoformat()})"
                )
                continue

            assignment.sync_role_rows_from_legacy_fields()
            synced += 1

        if dry_run:
            self.stdout.write(self.style.SUCCESS("Dry-run complete."))
            return

        self.stdout.write(
            self.style.SUCCESS(
                f"Backfill complete: synced normalized role rows for {synced} assignment(s)."
            )
        )
