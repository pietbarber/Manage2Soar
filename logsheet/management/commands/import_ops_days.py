import psycopg2
from django.core.management.base import BaseCommand
from django.conf import settings
from members.models import Member
from logsheet.models import Logsheet, Airfield

class Command(BaseCommand):
    help = "Import duty crew from legacy ops_days table into Logsheet model"

    def handle(self, *args, **options):

        from members.models import Member

        # Ensure import_bot exists
        import_user, created = Member.objects.get_or_create(
            username="import_bot",
            defaults={
                "first_name": "Import",
                "last_name": "From Legacy",
                "email": "import@skylinesoaring.org",
                "is_staff": True,
                "is_superuser": True,
            }
        )
        
        if created:
            self.stdout.write(self.style.SUCCESS("✅ Created import_bot user."))
        else:
            self.stdout.write(self.style.NOTICE("✔️ import_bot already exists."))
      
        self.stdout.write(self.style.NOTICE("Connecting to legacy ops_days via settings.DATABASES['legacy']..."))
      
        legacy = settings.DATABASES['legacy']
        conn = psycopg2.connect(
            dbname=legacy['NAME'],
            user=legacy['USER'],
            password=legacy['PASSWORD'],
            host=legacy.get('HOST', ''),
            port=legacy.get('PORT', ''),
        )

        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM ops_days ORDER BY flight_date ASC")
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
                self.stdout.write(self.style.WARNING(f"⚠️  No Airfield found for '{field}'"))
                continue

            logsheet = Logsheet.objects.filter(log_date=log_date, airfield=airfield).first()

            if not logsheet:
                logsheet = Logsheet.objects.create(
                    log_date=log_date,
                    airfield=airfield,
                    created_by=import_user,
                    finalized=True
                )
                self.stdout.write(self.style.SUCCESS(f"📝 Created empty logsheet for {log_date} @ {field}"))


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
                return Member.objects.filter(first_name__iexact=first, last_name__iexact=last).first()

            logsheet.duty_officer = resolve_member(data["dutyofficer"])
            logsheet.duty_instructor = resolve_member(data["instructor"])
            logsheet.assistant_duty_officer = resolve_member(data["assistant"])
            logsheet.tow_pilot = resolve_member(data["towpilot"])
            logsheet.surge_tow_pilot = resolve_member(data["am_towpilot"]) or resolve_member(data["pm_towpilot"])

            logsheet.save()
            updated += 1

        conn.close()
        self.stdout.write(self.style.SUCCESS(f"✅ Updated {updated} logsheets with duty crew from ops_days."))
