"""
Django management command to clean up old approved membership applications.

Usage:
    python manage.py cleanup_approved_applications
    python manage.py cleanup_approved_applications --days 30
    python manage.py cleanup_approved_applications --dry-run
"""

import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from members.models_applications import MembershipApplication

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Clean up membership applications that have been approved for more than N days (default: 365)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=365,
            help="Number of days to keep approved applications (default: 365)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be deleted without actually deleting",
        )

    def handle(self, *args, **options):
        days = options["days"]
        dry_run = options["dry_run"]
        cutoff_date = timezone.now() - timedelta(days=days)

        self.stdout.write(
            f"Looking for approved applications older than {days} days..."
        )
        self.stdout.write(f"Cutoff date: {cutoff_date.strftime('%Y-%m-%d %H:%M:%S')}")

        # Find approved applications older than cutoff date
        old_applications = MembershipApplication.objects.filter(
            status="approved", reviewed_at__lt=cutoff_date
        ).select_related("member_account")

        count = old_applications.count()

        if count == 0:
            self.stdout.write(
                self.style.SUCCESS(
                    "No approved applications found that are older than {} days.".format(
                        days
                    )
                )
            )
            return

        self.stdout.write(f"Found {count} approved application(s) to clean up:")

        for app in old_applications:
            days_old = (timezone.now() - app.reviewed_at).days if app.reviewed_at else 0
            member_info = (
                f" -> Member: {app.member_account.username}"
                if app.member_account
                else " (No linked member)"
            )
            self.stdout.write(
                f"  - {app.full_name} (ID: {app.application_id}) - {days_old} days old{member_info}"
            )

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    "DRY RUN: No applications were actually deleted. Use --dry-run=False to delete."
                )
            )
            return

        # Confirm deletion
        if (
            not options.get("verbosity", 1) == 0
        ):  # Skip confirmation in non-interactive mode
            confirm = input(
                f"\nAre you sure you want to delete {count} approved applications? [y/N]: "
            )
            if confirm.lower() != "y":
                self.stdout.write("Cleanup cancelled.")
                return

        # Perform deletion
        deleted_count = 0
        for app in old_applications:
            try:
                app_info = f"{app.full_name} (ID: {app.application_id})"
                app.delete()
                deleted_count += 1
                logger.info(f"Deleted approved application: {app_info}")
                self.stdout.write(f"  Deleted: {app_info}")
            except Exception as e:
                logger.error(f"Failed to delete application {app.application_id}: {e}")
                self.stdout.write(
                    self.style.ERROR(f"  Failed to delete {app.full_name}: {e}")
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully deleted {deleted_count} out of {count} approved applications."
            )
        )

        if deleted_count < count:
            self.stdout.write(
                self.style.WARNING(
                    f"{count - deleted_count} applications could not be deleted. Check logs for details."
                )
            )
