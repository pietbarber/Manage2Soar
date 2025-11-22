"""
Management command to fix YouTube iframe embeds in CMS content to prevent Error 153.

This command scans all CMS pages and homepage content for YouTube iframe embeds
and ensures they have the proper referrerpolicy="strict-origin-when-cross-origin"
attribute to prevent YouTube Error 153 playback issues.

Usage:
    python manage.py fix_youtube_embeds [--dry-run] [--force]

Options:
    --dry-run: Show what would be changed without making changes
    --force: Skip confirmation prompt
"""

import re

from django.core.management.base import BaseCommand

from cms.models import HomePageContent, Page


class Command(BaseCommand):
    help = "Fix YouTube iframe embeds to prevent Error 153"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be changed without making changes",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Skip confirmation prompt",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        force = options["force"]

        # Count how many items need fixing
        pages_to_fix = []
        homepage_to_fix = []

        # Check Pages
        for page in Page.objects.all():
            if self.needs_youtube_fix(page.content):
                pages_to_fix.append(page)

        # Check HomePageContent
        for homepage in HomePageContent.objects.all():
            if self.needs_youtube_fix(homepage.content):
                homepage_to_fix.append(homepage)

        total_fixes = len(pages_to_fix) + len(homepage_to_fix)

        if total_fixes == 0:
            self.stdout.write(
                self.style.SUCCESS(
                    "✅ No YouTube embeds need fixing - all are already correct!"
                )
            )
            return

        # Show what will be fixed
        self.stdout.write(
            self.style.WARNING(
                f"Found {total_fixes} items with YouTube embeds that need fixing:"
            )
        )

        if pages_to_fix:
            self.stdout.write(f"\n📄 Pages ({len(pages_to_fix)}):")
            for page in pages_to_fix:
                self.stdout.write(f"  • {page.title} (/{page.get_absolute_url()})")

        if homepage_to_fix:
            self.stdout.write(f"\n🏠 Homepage Content ({len(homepage_to_fix)}):")
            for homepage in homepage_to_fix:
                self.stdout.write(f"  • {homepage.title} [{homepage.audience}]")

        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    "\n🔍 DRY RUN: No changes were made. Run without --dry-run to apply fixes."
                )
            )
            return

        # Confirmation prompt
        if not force:
            self.stdout.write(
                f'\nThis will update {total_fixes} items to add referrerpolicy="strict-origin-when-cross-origin" to YouTube iframes.'
            )
            confirm = input("Continue? (y/N): ")
            if confirm.lower() != "y":
                self.stdout.write("❌ Cancelled.")
                return

        # Apply fixes
        fixes_applied = 0

        # Fix Pages - let model save() handle the fixing to avoid double-fix
        for page in pages_to_fix:
            old_content = page.content
            page.save()  # Model will automatically fix YouTube embeds
            # Re-check if content was actually modified
            page.refresh_from_db()
            if page.content != old_content:
                fixes_applied += 1
                self.stdout.write(f"✅ Fixed: {page.title}")

        # Fix HomePageContent - let model save() handle the fixing
        for homepage in homepage_to_fix:
            old_content = homepage.content
            homepage.save()  # Model will automatically fix YouTube embeds
            # Re-check if content was actually modified
            homepage.refresh_from_db()
            if homepage.content != old_content:
                fixes_applied += 1
                self.stdout.write(f"✅ Fixed: {homepage.title} [{homepage.audience}]")

        self.stdout.write(
            self.style.SUCCESS(
                f"\n🎉 Successfully fixed {fixes_applied} YouTube embeds!"
            )
        )
        self.stdout.write("All YouTube videos should now play without Error 153.")

    def needs_youtube_fix(self, content):
        """Check if content has YouTube iframes that need referrerpolicy fixing."""
        from cms.utils import needs_youtube_fix

        return needs_youtube_fix(content)
