import logging

import psycopg2
from django.conf import settings
from django.core.management.base import BaseCommand

from instructors.models import ClubQualificationType, MemberQualification
from members.models import Member

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Import member qualifications from legacy 'quals' table"

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.NOTICE(
                "Connecting to legacy database via settings.DATABASES['legacy']..."
            )
        )

        legacy = settings.DATABASES["legacy"]
        conn = psycopg2.connect(
            dbname=legacy["NAME"],
            user=legacy["USER"],
            password=legacy["PASSWORD"],
            host=legacy.get("HOST", ""),
            port=legacy.get("PORT", ""),
        )
        conn.set_client_encoding("WIN1252")
        cursor = conn.cursor()

        cursor.execute(
            "SELECT handle, role_name, is_qualified, expiration_date, instructor, notes FROM quals"
        )
        rows = cursor.fetchall()

        for (
            handle,
            role_name,
            is_qualified,
            expiration_date,
            instructor_handle,
            notes,
        ) in rows:
            try:
                member = Member.objects.get(legacy_username__iexact=handle)
            except Member.DoesNotExist:
                logger.warning(f"Member with handle '{handle}' not found. Skipping.")
                continue

            try:
                qual_type = ClubQualificationType.objects.get(code=role_name)
            except ClubQualificationType.DoesNotExist:
                logger.warning(f"Qualification type '{role_name}' not found. Skipping.")
                continue

            instructor = None
            if instructor_handle:
                try:
                    instructor = Member.objects.get(
                        legacy_username__iexact=instructor_handle
                    )
                except Member.DoesNotExist:
                    logger.warning(
                        f"Instructor '{instructor_handle}' not found for qualification '{role_name}' on '{handle}'."
                    )

            mq, created = MemberQualification.objects.update_or_create(
                member=member,
                qualification=qual_type,
                defaults={
                    "is_qualified": is_qualified,
                    "expiration_date": expiration_date,
                    "instructor": instructor,
                    "notes": notes or "",
                    "imported": True,
                },
            )

            action = "✅ Created" if created else "↺ Updated"
            self.stdout.write(f"{action}: {member.username} / {role_name}")

        cursor.close()
        conn.close()
        self.stdout.write(self.style.SUCCESS("Qualification import complete."))
