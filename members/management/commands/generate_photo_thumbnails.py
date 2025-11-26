"""
Management command to generate thumbnails for existing member profile photos.

This command backfills thumbnail images for members who already have profile
photos but are missing the medium (200x200) and/or small (64x64) thumbnails.

Works with both local file storage and cloud storage (GCS, S3, etc.).

Usage:
    python manage.py generate_photo_thumbnails          # Process all members
    python manage.py generate_photo_thumbnails --force  # Regenerate all thumbnails
    python manage.py generate_photo_thumbnails --dry-run  # Preview without saving
"""

import logging
import os
from io import BytesIO

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db.models import Q
from PIL import Image

from members.models import Member
from members.utils.image_processing import (
    THUMBNAIL_MEDIUM,
    THUMBNAIL_SMALL,
    create_square_thumbnail,
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Generate thumbnails for existing member profile photos"

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Regenerate thumbnails even if they already exist",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be done without making changes",
        )
        parser.add_argument(
            "--member-id",
            type=int,
            help="Process only a specific member ID",
        )

    def handle(self, *args, **options):
        force = options["force"]
        dry_run = options["dry_run"]
        member_id = options.get("member_id")

        # Build queryset - members with profile photos
        queryset = Member.objects.exclude(profile_photo="").exclude(
            profile_photo__isnull=True
        )

        if member_id:
            queryset = queryset.filter(id=member_id)

        if not force:
            # Only process members missing thumbnails
            queryset = queryset.filter(
                Q(profile_photo_small="")
                | Q(profile_photo_small__isnull=True)
                | Q(profile_photo_medium="")
                | Q(profile_photo_medium__isnull=True)
            )

        total = queryset.count()
        self.stdout.write(f"Found {total} members to process")

        if total == 0:
            self.stdout.write(self.style.SUCCESS("No members need processing"))
            return

        processed = 0
        skipped = 0
        errors = 0

        for member in queryset.iterator():
            photo_name = str(member.profile_photo)

            if dry_run:
                self.stdout.write(f"  Would process: {member.username} ({photo_name})")
                processed += 1
                continue

            try:
                # Read the photo from storage (works with both local and cloud storage)
                with member.profile_photo.open("rb") as photo_file:
                    img = Image.open(photo_file)
                    img.load()  # Force load before file closes
                    img = img.convert("RGB")

                # Generate thumbnails
                # Medium thumbnail
                medium = create_square_thumbnail(img, THUMBNAIL_MEDIUM)
                medium_buffer = BytesIO()
                medium.save(medium_buffer, format="JPEG", quality=85, optimize=True)
                medium_content = ContentFile(medium_buffer.getvalue())

                # Small thumbnail
                small = create_square_thumbnail(img, THUMBNAIL_SMALL)
                small_buffer = BytesIO()
                small.save(small_buffer, format="JPEG", quality=85, optimize=True)
                small_content = ContentFile(small_buffer.getvalue())

                # Get base filename for thumbnails
                base_name = os.path.basename(photo_name)
                # Convert to jpg extension
                name_without_ext = os.path.splitext(base_name)[0]
                medium_name = f"medium_{name_without_ext}.jpg"
                small_name = f"small_{name_without_ext}.jpg"

                # Save thumbnails
                member.profile_photo_medium.save(
                    medium_name, medium_content, save=False
                )
                member.profile_photo_small.save(small_name, small_content, save=False)

                # Save the member
                member.save(
                    update_fields=["profile_photo_medium", "profile_photo_small"]
                )

                self.stdout.write(
                    self.style.SUCCESS(f"  Generated thumbnails for: {member.username}")
                )
                processed += 1

            except FileNotFoundError:
                self.stdout.write(
                    self.style.WARNING(
                        f"  Skipping {member.username}: photo file not found"
                    )
                )
                skipped += 1
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"  Error processing {member.username}: {e}")
                )
                errors += 1
                logger.exception(f"Error generating thumbnails for {member.username}")

        # Summary
        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"Processed: {processed}, Skipped: {skipped}, Errors: {errors}"
            )
        )

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - no changes were made"))
