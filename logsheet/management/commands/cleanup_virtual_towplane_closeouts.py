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
        virtual_closeouts = TowplaneCloseout.objects.filter(
            towplane__n_number__iregex=r"^(SELF|WINCH|OTHER)$"
        ).select_related("towplane", "logsheet")

        to_delete = []

        for closeout in virtual_closeouts:
            n_number = closeout.towplane.n_number.upper()

            # Always delete WINCH and OTHER closeouts
            if n_number in {"WINCH", "OTHER"}:
                to_delete.append(closeout)
                continue

            # For SELF, only keep if used with club-owned gliders
            if n_number == "SELF":
                has_club_glider = closeout.logsheet.flights.filter(
                    towplane=closeout.towplane, glider__club_owned=True
                ).exists()

                if not has_club_glider:
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
                f"  - Logsheet {closeout.logsheet.date} ({closeout.logsheet.pk}): "
                f"{closeout.towplane.name} ({closeout.towplane.n_number})"
            )

        if dry_run:
            self.stdout.write(
                self.style.WARNING("\nDRY RUN - No closeouts were deleted")
            )
            self.stdout.write("Run without --dry-run to actually delete these records")
        else:
            # Actually delete the closeouts
            count = len(to_delete)
            for closeout in to_delete:
                closeout.delete()

            self.stdout.write(
                self.style.SUCCESS(
                    f"\nSuccessfully deleted {count} stale virtual towplane closeouts"
                )
            )
