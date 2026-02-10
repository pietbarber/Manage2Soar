"""
Management command to clean up stale virtual towplane closeouts.

Removes TowplaneCloseout entries for WINCH, OTHER, and SELF (when used with
private gliders) that were created before Issue #623 fixes were implemented.

Usage:
    python manage.py cleanup_virtual_towplane_closeouts --dry-run
    python manage.py cleanup_virtual_towplane_closeouts
"""

from django.core.management.base import BaseCommand

from logsheet.models import TowplaneCloseout


class Command(BaseCommand):
    help = "Clean up stale virtual towplane closeouts (SELF/WINCH/OTHER)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be deleted without actually deleting",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        if dry_run:
            self.stdout.write(
                self.style.WARNING("DRY RUN MODE - No changes will be made")
            )

        # Find all closeouts for virtual towplanes
        # Reuse centralized logic from get_relevant_towplanes
        from collections import defaultdict

        from logsheet.utils.towplane_utils import get_relevant_towplanes

        virtual_closeouts = (
            TowplaneCloseout.objects.filter(
                towplane__n_number__iregex=r"^(SELF|WINCH|OTHER)$"
            )
            .select_related("towplane", "logsheet")
            .order_by("logsheet_id")
        )

        # Group closeouts by logsheet to avoid repeated get_relevant_towplanes() calls
        closeouts_by_logsheet = defaultdict(list)
        for closeout in virtual_closeouts:
            closeouts_by_logsheet[closeout.logsheet_id].append(closeout)

        to_delete = []

        # Process each logsheet once, caching relevant towplane IDs
        for logsheet_id, closeouts in closeouts_by_logsheet.items():
            # Get relevant towplanes for this logsheet once
            logsheet = closeouts[0].logsheet  # All closeouts share the same logsheet
            relevant_towplane_ids = set(
                get_relevant_towplanes(logsheet).values_list("pk", flat=True)
            )

            # Check each closeout against the cached relevant set
            for closeout in closeouts:
                if closeout.towplane_id not in relevant_towplane_ids:
                    to_delete.append(closeout)

        if not to_delete:
            self.stdout.write(
                self.style.SUCCESS("No stale virtual towplane closeouts found")
            )
            return

        # Report what will be deleted
        self.stdout.write(
            self.style.WARNING(f"\nFound {len(to_delete)} stale closeouts:")
        )

        for closeout in to_delete:
            self.stdout.write(
                f"  - Logsheet {closeout.logsheet.log_date} ({closeout.logsheet.pk}): "
                f"{closeout.towplane.name} ({closeout.towplane.n_number})"
            )

        if dry_run:
            self.stdout.write(
                self.style.WARNING("\nDRY RUN - No closeouts were deleted")
            )
            self.stdout.write("Run without --dry-run to actually delete these records")
        else:
            # Actually delete the closeouts in bulk
            count = len(to_delete)
            TowplaneCloseout.objects.filter(
                pk__in=[closeout.pk for closeout in to_delete]
            ).delete()

            self.stdout.write(
                self.style.SUCCESS(
                    f"\nSuccessfully deleted {count} stale virtual towplane closeouts"
                )
            )
