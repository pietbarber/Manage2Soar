import psycopg2
from django.conf import settings
from django.core.management.base import BaseCommand

from logsheet.models import Airfield, Logsheet, TowplaneCloseout
from logsheet.utils.aliases import resolve_towplane


class Command(BaseCommand):
    help = "Import towplane closeout data from legacy towplane_data table"

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Connecting to legacy towplane_data..."))

        legacy = settings.DATABASES["legacy"]
        conn = psycopg2.connect(
            dbname=legacy["NAME"],
            user=legacy["USER"],
            password=legacy["PASSWORD"],
            host=legacy.get("HOST", ""),
            port=legacy.get("PORT", ""),
        )

        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM towplane_data ORDER BY flight_date ASC")
            columns = [col[0] for col in cursor.description]
            rows = cursor.fetchall()

        created = 0
        skipped = 0

        for row in rows:
            data = dict(zip(columns, row))
            log_date = data["flight_date"]
            field = (data.get("field") or "").strip()
            towplane_name = data.get("towplane", "")
            comment = data.get("towpilot_comments", "")

            try:
                airfield = Airfield.objects.get(identifier=field)
                logsheet = Logsheet.objects.get(log_date=log_date, airfield=airfield)
            except (Airfield.DoesNotExist, Logsheet.DoesNotExist):
                self.stdout.write(
                    self.style.WARNING(
                        f"⚠️  No Logsheet for {log_date} @ {field} — skipping"
                    )
                )
                skipped += 1
                continue

            towplane = resolve_towplane(towplane_name, log_date, comment)
            if towplane:
                print(f"✅ Resolved towplane '{towplane}' for {log_date}")
            tach = data["tach_time"]

            if tach and abs(tach) > 9999:
                print(f"⚠️  Skipping absurd tach_time={tach} on {log_date}")
                skipped += 1
                continue

            if not towplane:
                skipped += 1
                continue

            closeout, created_new = TowplaneCloseout.objects.get_or_create(
                logsheet=logsheet,
                towplane=towplane,
                defaults={
                    "start_tach": data["start_tach"],
                    "end_tach": data["stop_tach"],
                    "tach_time": data["tach_time"],
                    "fuel_added": data["gas_added"],
                    "notes": comment or "",
                },
            )

            if created_new:
                created += 1

        conn.close()
        self.stdout.write(
            self.style.SUCCESS(f"✅ Created {created} TowplaneCloseout records.")
        )
        self.stdout.write(
            self.style.NOTICE(
                f"⚠️ Skipped {skipped} due to missing logsheets, towplanes, or winch/canceled ops."
            )
        )
