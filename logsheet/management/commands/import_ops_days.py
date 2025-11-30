import psycopg2
from django.conf import settings
from django.core.management.base import BaseCommand

from logsheet.models import Airfield, Logsheet
from members.models import Member


class Command(BaseCommand):
    help = "Import duty crew from legacy ops_days table into Logsheet model"

    def add_arguments(self, parser):
        parser.add_argument(
            "--date",
            type=str,
            help="Only import ops_days on or after this date (YYYY-MM-DD)",
        )

    def handle(self, *args, **options):

        # Ensure import_bot exists
        import_user, created = Member.objects.get_or_create(
            username="import_bot",
            defaults={
                "first_name": "Import",
                "last_name": "From Legacy",
                "email": "import@skylinesoaring.org",
                "is_staff": True,
                "is_superuser": True,
            },
        )

        if created:
            self.stdout.write(self.style.SUCCESS("✅ Created import_bot user."))
        else:
            self.stdout.write(self.style.NOTICE("✔️ import_bot already exists."))

        self.stdout.write(
            self.style.NOTICE(
                "Connecting to legacy ops_days via settings.DATABASES['legacy']..."
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

        with conn.cursor() as cursor:
            date_arg = options.get("date")
            if date_arg:
                self.stdout.write(
                    self.style.NOTICE(f"Importing ops_days on or after {date_arg}")
                )
                cursor.execute(
                    "SELECT * FROM ops_days WHERE flight_date >= %s ORDER BY flight_date ASC",
                    [date_arg],
                )
            else:
                cursor.execute("SELECT * FROM ops_days ORDER BY flight_date ASC")
            if cursor.description is None:
                self.stdout.write(
                    self.style.ERROR("❌ No columns returned from ops_days query!")
                )
                return
            columns = [col[0] for col in cursor.description]
            rows = cursor.fetchall()

        updated = 0
        for row in rows:
            data = dict(zip(columns, row))
            log_date = data["flight_date"]
            field = data["field"].strip()

            try:
                airfield = Airfield.objects.get(identifier=field)
            except Airfield.DoesNotExist:
                self.stdout.write(
                    self.style.WARNING(f"⚠️  No Airfield found for '{field}'")
                )
                continue

            logsheet = Logsheet.objects.filter(
                log_date=log_date, airfield=airfield
            ).first()

            if not logsheet:
                logsheet = Logsheet.objects.create(
                    log_date=log_date,
                    airfield=airfield,
                    created_by=import_user,
                    finalized=True,
                )
                self.stdout.write(
                    self.style.SUCCESS(
                        f"📝 Created empty logsheet for {log_date} @ {field}"
                    )
                )

            def resolve_member(name):
                if not name:
                    return None
                name = name.strip()

                # Try legacy_username match first
                member = Member.objects.filter(legacy_username__iexact=name).first()
                if member:
                    return member

                # Fallback to first + last name
                parts = name.split()
                if len(parts) < 2:
                    return None
                first, last = parts[0], parts[-1]
                return Member.objects.filter(
                    first_name__iexact=first, last_name__iexact=last
                ).first()

            logsheet.duty_officer = resolve_member(data["dutyofficer"])
            logsheet.duty_instructor = resolve_member(data["instructor"])
            logsheet.assistant_duty_officer = resolve_member(data["assistant"])

            # Tow pilot mapping logic:
            # - If 'towpilot' is present, use as primary tow pilot.
            # - If both 'am_towpilot' and 'pm_towpilot' are present and different, assign one as surge.
            # - If only one of am/pm is present, use as surge tow pilot.
            # - If 'towpilot' is missing but am/pm present, assign am/pm as primary and surge as possible.
            towpilot = resolve_member(data.get("towpilot"))
            am_towpilot = resolve_member(data.get("am_towpilot"))
            pm_towpilot = resolve_member(data.get("pm_towpilot"))

            if towpilot:
                logsheet.tow_pilot = towpilot
                # If am/pm are present and different from towpilot, assign as surge
                surge_candidates = [
                    p for p in (am_towpilot, pm_towpilot) if p and p != towpilot
                ]
                logsheet.surge_tow_pilot = (
                    surge_candidates[0] if surge_candidates else None
                )
                if am_towpilot and pm_towpilot and am_towpilot != pm_towpilot:
                    self.stdout.write(
                        self.style.WARNING(
                            f"⚠️  Both AM and PM tow pilots differ for {log_date} @ {field}. AM: {am_towpilot}, PM: {pm_towpilot}"
                        )
                    )
            elif am_towpilot or pm_towpilot:
                # If no main towpilot, but am/pm present, assign am as main, pm as surge (if different)
                logsheet.tow_pilot = am_towpilot or pm_towpilot
                if am_towpilot and pm_towpilot and am_towpilot != pm_towpilot:
                    logsheet.surge_tow_pilot = pm_towpilot
                    self.stdout.write(
                        self.style.WARNING(
                            f"⚠️  No main towpilot, but both AM and PM present and differ for {log_date} @ {field}. AM: {am_towpilot}, PM: {pm_towpilot}"
                        )
                    )
                else:
                    logsheet.surge_tow_pilot = None
            else:
                logsheet.tow_pilot = None
                logsheet.surge_tow_pilot = None
                self.stdout.write(
                    self.style.WARNING(f"⚠️  No tow pilot info for {log_date} @ {field}")
                )

            logsheet.save()
            updated += 1

        conn.close()
        self.stdout.write(
            self.style.SUCCESS(
                f"✅ Updated {updated} logsheets with duty crew from ops_days."
            )
        )
