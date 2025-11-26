"""
Management command to generate thumbnails for existing equipment photos.

This command processes all Glider and Towplane records that have photos
but are missing thumbnails. It works with cloud storage (GCS) by
downloading the original photo, generating thumbnails, and uploading them.

Usage:
    python manage.py generate_equipment_thumbnails
    python manage.py generate_equipment_thumbnails --dry-run
    python manage.py generate_equipment_thumbnails --force
    python manage.py generate_equipment_thumbnails --glider-id 5
    python manage.py generate_equipment_thumbnails --towplane-id 3
"""

import logging

from django.core.management.base import BaseCommand

from logsheet.models import Glider, Towplane
from logsheet.utils.image_processing import generate_equipment_thumbnails

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Generate thumbnails for existing equipment photos"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be done without making changes",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Regenerate thumbnails even if they already exist",
        )
        parser.add_argument(
            "--glider-id",
            type=int,
            help="Process only this specific glider",
        )
        parser.add_argument(
            "--towplane-id",
            type=int,
            help="Process only this specific towplane",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        force = options["force"]
        glider_id = options.get("glider_id")
        towplane_id = options.get("towplane_id")

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - no changes will be made"))

        # Process gliders
        gliders = Glider.objects.all()
        if glider_id:
            gliders = gliders.filter(id=glider_id)

        glider_count = 0
        glider_errors = 0

        for glider in gliders:
            if not glider.photo:
                continue

            # Skip if thumbnails exist and not forcing
            if not force and glider.photo_medium and glider.photo_small:
                self.stdout.write(
                    f"  Skipping glider {glider.n_number} - thumbnails exist"
                )
                continue

            self.stdout.write(f"Processing glider {glider.n_number}...")

            if dry_run:
                self.stdout.write(f"  Would generate thumbnails for {glider.n_number}")
                glider_count += 1
                continue

            try:
                # Read the original photo - works with cloud storage
                glider.photo.seek(0)
                thumbnails = generate_equipment_thumbnails(glider.photo)

                # Get base filename
                base_name = glider.photo.name.split("/")[-1]

                # Save thumbnails
                glider.photo_medium.save(
                    f"medium_{base_name}", thumbnails["medium"], save=False
                )
                glider.photo_small.save(
                    f"small_{base_name}", thumbnails["small"], save=False
                )
                glider.save(update_fields=["photo_medium", "photo_small"])

                self.stdout.write(
                    self.style.SUCCESS(
                        f"  ✓ Generated thumbnails for {glider.n_number}"
                    )
                )
                glider_count += 1

            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"  ✗ Error processing {glider.n_number}: {e}")
                )
                glider_errors += 1

        # Process towplanes
        towplanes = Towplane.objects.all()
        if towplane_id:
            towplanes = towplanes.filter(id=towplane_id)

        towplane_count = 0
        towplane_errors = 0

        for towplane in towplanes:
            if not towplane.photo:
                continue

            # Skip if thumbnails exist and not forcing
            if not force and towplane.photo_medium and towplane.photo_small:
                self.stdout.write(
                    f"  Skipping towplane {towplane.n_number} - thumbnails exist"
                )
                continue

            self.stdout.write(f"Processing towplane {towplane.n_number}...")

            if dry_run:
                self.stdout.write(
                    f"  Would generate thumbnails for {towplane.n_number}"
                )
                towplane_count += 1
                continue

            try:
                # Read the original photo - works with cloud storage
                towplane.photo.seek(0)
                thumbnails = generate_equipment_thumbnails(towplane.photo)

                # Get base filename
                base_name = towplane.photo.name.split("/")[-1]

                # Save thumbnails
                towplane.photo_medium.save(
                    f"medium_{base_name}", thumbnails["medium"], save=False
                )
                towplane.photo_small.save(
                    f"small_{base_name}", thumbnails["small"], save=False
                )
                towplane.save(update_fields=["photo_medium", "photo_small"])

                self.stdout.write(
                    self.style.SUCCESS(
                        f"  ✓ Generated thumbnails for {towplane.n_number}"
                    )
                )
                towplane_count += 1

            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"  ✗ Error processing {towplane.n_number}: {e}")
                )
                towplane_errors += 1

        # Summary
        self.stdout.write("\n" + "=" * 50)
        action = "Would process" if dry_run else "Processed"
        self.stdout.write(f"{action} {glider_count} gliders, {glider_errors} errors")
        self.stdout.write(
            f"{action} {towplane_count} towplanes, {towplane_errors} errors"
        )

        if dry_run:
            self.stdout.write(
                self.style.WARNING("\nDRY RUN complete - no changes were made")
            )
        else:
            self.stdout.write(self.style.SUCCESS("\nThumbnail generation complete!"))
