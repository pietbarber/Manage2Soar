import logging
from datetime import date

import psycopg2
from django.conf import settings
from django.core.management.base import BaseCommand

from members.models import Badge, Member, MemberBadge

logger = logging.getLogger(__name__)

BADGE_NAME_MAP = {
    "A": "A Badge",
    "B": "B Badge",
    "C": "C Badge",
    "Silver Badge": "FAI Silver Badge",
    "Gold Badge": "FAI Gold Badge",
    "Diamond Badge": "FAI Diamond Badge",
    "Silver Distance": "Silver Distance",
    "Silver Altitude": "Silver Altitude",
    "Silver Duration": "Silver Duration",
    "Gold Distance": "Gold Distance",
    "Gold Altitude": "Gold Altitude",
    "Diamond Distance": "Diamond Distance",
    "Diamond Altitude": "Diamond Altitude",
    "Diamond Goal": "Diamond Goal",
    "Bronze Badge": "Bronze Badge",
}


class Command(BaseCommand):
    help = "Import earned member badges from the legacy 'badges_earned' table"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true", help="Run without saving changes"
        )
        parser.add_argument(
            "--update-ssa-urls",
            action="store_true",
            help="Import SSA badge URLs from legacy badge_link table",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        update_ssa_urls = options["update_ssa_urls"]
        msg = "Connecting to legacy database via settings.DATABASES['legacy']..."
        self.stdout.write(self.style.NOTICE(msg))

        legacy = settings.DATABASES["legacy"]
        conn = psycopg2.connect(
            dbname=legacy["NAME"],
            user=legacy["USER"],
            password=legacy["PASSWORD"],
            host=legacy.get("HOST", ""),
            port=legacy.get("PORT", ""),
        )
        conn.set_client_encoding("WIN1252")

        if update_ssa_urls:
            with conn.cursor() as cursor:
                cursor.execute("SELECT handle, url FROM badge_link")
                url_rows = cursor.fetchall()

            updated = 0
            skipped = 0
            for handle, url in url_rows:
                handle = handle.strip()
                url = url.strip()
                try:
                    member = Member.objects.get(legacy_username=handle)
                except Member.DoesNotExist:
                    logger.warning(
                        "No member found for handle '%s', skipping SSA URL",
                        handle,
                    )
                    skipped += 1
                    continue

                if dry_run:
                    msg = f"[DRY RUN] Would set SSA URL for {member} to {url}"
                    self.stdout.write(msg)
                else:
                    member.ssa_url = url
                    member.save(update_fields=["ssa_url"])
                    msg = f"Set SSA URL for {member} to {url}"
                    self.stdout.write(msg)

                updated += 1
            total = updated + skipped
            summary = (
                "SSA URL import complete. Total processed: "
                + str(total)
                + ", Updated: "
                + str(updated)
                + ", Skipped: "
                + str(skipped)
            )
            self.stdout.write(self.style.SUCCESS(summary))
            # If only updating SSA URLs, exit early
            if not dry_run:
                return

        # Continue with badge import as before
        with conn.cursor() as cursor:
            cursor.execute("SELECT handle, badge, earned_date FROM badges_earned")
            rows = cursor.fetchall()

        imported = 0
        skipped = 0

        for handle, badge_name, earned_date in rows:
            handle = handle.strip()
            badge_name = badge_name.strip()
            badge_name = BADGE_NAME_MAP.get(badge_name, badge_name)

            try:
                member = Member.objects.get(legacy_username=handle)
            except Member.DoesNotExist:
                logger.warning(
                    "No member found for handle '%s', skipping badge '%s'",
                    handle,
                    badge_name,
                )
                skipped += 1
                continue

            try:
                badge = Badge.objects.get(name__iexact=badge_name)
            except Badge.DoesNotExist:
                logger.warning(
                    "Badge '%s' not found, skipping for %s", badge_name, handle
                )
                skipped += 1
                continue

            if dry_run:
                msg = f"[DRY RUN] Would assign {badge_name} to {member}"
                self.stdout.write(msg)
            else:
                mb, created = MemberBadge.objects.get_or_create(
                    member=member,
                    badge=badge,
                    defaults={
                        "date_awarded": earned_date or date.today(),
                        "notes": "",
                    },
                )
                if created:
                    msg = f"Assigned {badge_name} to {member}"
                    self.stdout.write(msg)
                else:
                    msg = (
                        f"{badge_name} already exists for {member}, "
                        "skipping"
                    )
                    self.stdout.write(msg)
            imported += 1

        total = imported + skipped
        summary = (
            "Import complete. Total processed: "
            + str(total)
            + ", Imported: "
            + str(imported)
            + ", Skipped: "
            + str(skipped)
        )
        self.stdout.write(self.style.SUCCESS(summary))
