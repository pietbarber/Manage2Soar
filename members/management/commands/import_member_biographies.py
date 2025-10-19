import logging
from datetime import datetime

import psycopg2
from django.conf import settings
from django.core.management.base import BaseCommand

from members.models import Biography, Member

logger = logging.getLogger(__name__)


def sanitize(text):
    if not text:
        return ""
    try:
        cleaned = text.encode("cp1252", errors="ignore").decode(
            "utf-8", errors="ignore"
        )
        return cleaned.replace("\r", "").strip()
    except Exception as e:
        logger.warning(f"Failed to sanitize text: {e}")
        return ""


class Command(BaseCommand):
    help = "Import member biographies from legacy 'bios' table using psycopg2"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true", help="Run without saving changes"
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        notice_msg = (
            "Connecting to legacy database via settings.DATABASES['legacy']..."
        )
        self.stdout.write(self.style.NOTICE(notice_msg))

        legacy = settings.DATABASES["legacy"]
        conn = psycopg2.connect(
            dbname=legacy["NAME"],
            user=legacy["USER"],
            password=legacy["PASSWORD"],
            host=legacy.get("HOST", ""),
            port=legacy.get("PORT", ""),
        )
        conn.set_client_encoding("WIN1252")

        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM bios")
            if cursor.description is None:
                columns = []
            else:
                # psycopg2 cursor.description is a sequence of tuples; the
                # first element is the column name.
                columns = [desc[0] for desc in cursor.description]
            rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

        imported = 0

        for row in rows:
            handle = row["handle"].strip()
            raw_bio = row.get("bio_body", "")
            raw_date = row.get("lastupdated")

            content = sanitize(raw_bio)
            last_updated = raw_date or datetime.now()

            try:
                member = Member.objects.get(legacy_username=handle)
            except Member.DoesNotExist:
                self.stdout.write(
                    self.style.WARNING(
                        f"Skipping: No matching member for handle {handle}"
                    )
                )
                continue

            if dry_run:
                self.stdout.write(f"[DRY RUN] Would import bio for {member}")
            else:
                biography, _ = Biography.objects.get_or_create(member=member)
                biography.content = content
                biography.last_updated = last_updated
                biography.save()
                self.stdout.write(f"Imported biography for {member}")
            imported += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Import complete. Total biographies processed: {imported}"
            )
        )
