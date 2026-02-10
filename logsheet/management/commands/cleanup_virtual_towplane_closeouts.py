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
        from logsheet.utils.towplane_utils import get_relevant_towplanes

        virtual_closeouts = TowplaneCloseout.objects.filter(
            towplane__n_number__iregex=r"^(SELF|WINCH|OTHER)$"
        ).select_related("towplane", "logsheet")

        to_delete = []

        for closeout in virtual_closeouts:
            # Use centralized logic to determine if this closeout should exist
            relevant_towplanes = get_relevant_towplanes(closeout.logsheet)

            # If this towplane is not in the relevant set, mark for deletion
            if closeout.towplane not in relevant_towplanes:
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
