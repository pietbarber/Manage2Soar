# logsheet/management/commands/import_legacy_flights.py

from django.core.management.base import BaseCommand
from django.db import connection
from logsheet.models import Flight, Logsheet, Glider, Towplane
from members.models import Member
from datetime import datetime, timedelta, date, time
from decimal import Decimal

import psycopg2
from django.conf import settings
from logsheet.models import Airfield
from logsheet.utils.aliases import resolve_towplane



GLIDER_ALIASES = [

    {"legacy_name": "XZ", "start": "2000-01-02", "end": "2019-07-01", "n_number": "N27SN"},
    {"legacy_name": "XZ", "start": "2019-07-07", "end": "2099-12-31", "n_number": "N727AM"},
    {"legacy_name": "Russia", "start": "2000-01-02", "end": "2020-02-28", "n_number": "N912ES"},
    {"legacy_name": "Russia", "start": "2020-03-01", "end": "2099-12-31", "n_number": "N1051R"},

    {"legacy_name": "GROB 103", "n_number": "N4794E"},
    {"legacy_name": "SGS 1-36", "n_number": "N3617B"},
    {"legacy_name": "6E", "n_number": "N6108J"},
    {"legacy_name": "N341KS", "n_number": "N341KS"},
    {"legacy_name": "N321K", "n_number": "N321K"},
    {"legacy_name": "N2671H", "n_number": "N2671H"},
    {"legacy_name": "CAPSTAN", "n_number": "N7475"},
    {"legacy_name": "Private", "n_number": "Unknown"},

    {"legacy_name": "Bergfalke", "n_number": "N0002"}, # Asked Bill Burner for its current whereabouts
    {"legacy_name": "1FW", "n_number": "N0004"}, # This is Fred Winters old LS4 that he crashed, and no record of its N number
    {"legacy_name": "BG", "n_number": "N0005"},  # Mike Peterson, contacted to get N number. 
    {"legacy_name": "PM", "n_number": "N8RX"}, # This may be the same glider as SF


    {"legacy_name": "9X", "n_number": "N270AS"}, # Asked george Hazelrigg for its N number
    {"legacy_name": "Cirrus", "n_number": "N888AN"},
    {"legacy_name": "PW5", "n_number": "N505CC"},
    {"legacy_name": "H3", "n_number": "N16AL"},
    {"legacy_name": "9Y", "n_number": "N520RJ"},
    {"legacy_name": "CI", "n_number": "N184W"}, # Kevin Fleet's Libelle; Got it from Ginny Pawlak, she found his logbook
    {"legacy_name": "JS", "n_number": "N370JS"},
    {"legacy_name": "TO", "n_number": "N606RM"},
    {"legacy_name": "QQ", "n_number": "N483KS"},
    {"legacy_name": "289", "n_number": "N2781Z"},
    {"legacy_name": "BW", "n_number": "N52BW"},
    {"legacy_name": "NG", "n_number": "N10MG"},
    {"legacy_name": "WV", "n_number": "N99WV"},
    {"legacy_name": "PE", "n_number": "N6800"},
    {"legacy_name": "RW", "n_number": "N531RW"},
    {"legacy_name": "470", "n_number": "N470BD"},
    {"legacy_name": "HR", "n_number": "N84HR"},
    {"legacy_name": "SF", "n_number": "N8RX"},
    {"legacy_name": "LAK12", "n_number": "N12LY"},
    {"legacy_name": "N12LY", "n_number": "N12LY"},
    {"legacy_name": "LAK-12", "n_number": "N12LY"},
    {"legacy_name": "BB", "n_number": "N3464R"},
    {"legacy_name": "316", "n_number": "N126JL"},
    {"legacy_name": "238", "n_number": "N2710Z"},
    {"legacy_name": "505", "n_number": "N1115S"},
    {"legacy_name": "3B", "n_number": "N31L"},
    {"legacy_name": "235", "n_number": "N2703Z"},
    {"legacy_name": "FW", "n_number": "N325AD"},
    {"legacy_name": "ZR", "n_number": "N512ZR"},
    {"legacy_name": "AE", "n_number": "N343JG"},
    {"legacy_name": "160", "n_number": "N8627R"},
    {"legacy_name": "GWZ", "n_number": "N15BT"},
    {"legacy_name": "SM", "n_number": "N2617H"},
    {"legacy_name": "SG", "n_number": "D-KUHR"},
    {"legacy_name": "SZ", "n_number": "N483SZ"},
    {"legacy_name": "SGS 2-33", "n_number": "N2724H"},
    {"legacy_name": "CP", "n_number": "N1XE"},
    {"legacy_name": "UU", "n_number": "N11UU"},
]

def resolve_glider(legacy_name, flight_date):
    """Resolves glider by legacy name and optional date range."""
    if not legacy_name:
        return None

    name = legacy_name.strip().upper()
    date_str = str(flight_date)

    match = None
    for entry in GLIDER_ALIASES:
        if entry["legacy_name"].strip().upper() == name:
            if "start" in entry and "end" in entry:
                if entry["start"] <= date_str <= entry["end"]:
                    match = entry
                    break
            else:
                match = entry  # no date constraints

    if match:
        return Glider.objects.filter(n_number=match["n_number"]).first()

    print(f"⚠️  Glider not resolved for legacy name '{legacy_name}' on {flight_date}")
    return None

def find_member_by_name(name):
    """
    Tries to match a name to legacy_username first, then falls back to first_name + last_name.
    """
    if not name:
        return None
    name = name.strip()

    # 1. Match legacy_username
    member = Member.objects.filter(legacy_username__iexact=name).first()
    if member:
        return member

    # 2. Fallback: match by first and last name
    parts = name.split()
    if len(parts) < 2:
        return None
    first, last = parts[0], parts[-1]
    return Member.objects.filter(first_name__iexact=first, last_name__iexact=last).first()


from members.models import Member

class Command(BaseCommand):
    help = "Import legacy flights from PostgreSQL flight_info table"

    def handle(self, *args, **options):

        from members.models import Member

        # Ensure import_bot exists (idempotent)
        import_user, created = Member.objects.get_or_create(
            username="import_bot",
            defaults={
                "first_name": "Import",
                "last_name": "from Legacy",
                "email": "webmaster@skylinesoaring.org",
                "is_staff": True,
                "is_superuser": True,  # optional, but helps with access
            }
        )

        if created:
            self.stdout.write(self.style.SUCCESS("✅ Created import_bot user."))
        else:
            self.stdout.write(self.style.NOTICE("✔️ import_bot already exists."))

        import_user = Member.objects.filter(username="import_bot").first()
        print(import_user)

        self.stdout.write(self.style.NOTICE("Connecting to legacy database via settings.DATABASES['legacy']..."))

        legacy = settings.DATABASES['legacy']
        conn = psycopg2.connect(
            dbname=legacy['NAME'],
            user=legacy['USER'],
            password=legacy['PASSWORD'],
            host=legacy.get('HOST', ''),
            port=legacy.get('PORT', ''),
        )

        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM flight_info2 ORDER BY flight_date ASC")
            columns = [col[0] for col in cursor.description]
            rows = cursor.fetchall()

        count = 0
        for row in rows:
            data = dict(zip(columns, row))
            towplane_name = data.get("towplane") or ""
            towplane_obj = None
            
            if towplane_name:
                towplane_obj = resolve_towplane(data.get("towplane"), data.get("flight_date"), comment="")
                if not towplane_obj:
                    print(f"⚠️ No towplane matched for '{towplane_name}' on flight {data['flight_tracking_id']}")

            count += 1
            #print(f"Importing flight #{data['flight_tracking_id']} on {data['flight_date']}")
            print (".")

            # --- Resolve related objects ---
            pilot = find_member_by_name(data["pilot"])
            instructor = find_member_by_name(data["instructor"])
            passenger = find_member_by_name(data["passenger"])
            towpilot = find_member_by_name(data["towpilot"])

            # Glider by registration/N-number
            glider = resolve_glider(data["glider"], data["flight_date"])
            airfield=Airfield.objects.get(identifier=data["field"].strip())
 
            # Logsheet by date + field (assumes pre-imported or create-on-demand)
            logsheet, _ = Logsheet.objects.get_or_create(
                log_date=data["flight_date"],
                airfield=airfield,
                defaults={
                    "created_by": import_user,
                    "default_towplane": None,
                    "duty_officer": None,
                    "finalized": True
                    },  # Required if creating — fill as needed
            )

            # Parse times
            def parse_time(t): return t if isinstance(t, time) else None

            # --- Deduplicate old flights ---
            towpilot = find_member_by_name(data["towpilot"])
            glider = resolve_glider(data["glider"], data["flight_date"])
            airfield = Airfield.objects.get(identifier=data["field"].strip())
            launch_time = parse_time(data["takeoff_time"])
            landing_time = parse_time(data["landing_time"])
            
            # Fetch or create the Logsheet
            logsheet, _ = Logsheet.objects.get_or_create(
                log_date=data["flight_date"],
                airfield=airfield,
                defaults={
                    "created_by": import_user,
                    "default_towplane": None,
                    "duty_officer": None,
                    "finalized": True,
                },
            )
            
            # Try to find an existing matching flight
            possible_dupes = Flight.objects.filter(
                logsheet=logsheet,
                glider=glider,
                pilot=pilot,
                instructor=instructor,
                launch_time=launch_time,
                landing_time=landing_time,
                passenger=passenger,
            )
            
            # Check for a dupe with same or null towplane
            if possible_dupes.filter(towplane=towplane_obj).exists() or possible_dupes.filter(towplane__isnull=True).exists():
                print(f"🧹 Removing old flight to re-import with updated towplane: {data['flight_date']} / {data['pilot']}")
                possible_dupes.delete()

            # --- Now create the new Flight ---
            flight = Flight(
                logsheet=logsheet,
                glider=glider,
                launch_time=launch_time,
                landing_time=landing_time,
                duration=None,
            
                pilot=pilot,
                guest_pilot_name=data["pilot"] if not pilot else "",
                legacy_pilot_name=data["pilot"],
            
                instructor=instructor,
                guest_instructor_name=data["instructor"] if not instructor and data["instructor"] else "",
                legacy_instructor_name=data["instructor"] or "",
            
                passenger=passenger,
                passenger_name=data["passenger"] if not passenger and data["passenger"] else "",
                legacy_passenger_name=data["passenger"] or "",
            
                tow_pilot=towpilot,
                guest_towpilot_name=data["towpilot"] if not towpilot and data["towpilot"] else "",
                legacy_towpilot_name=data["towpilot"] or "",

                towplane=towplane_obj,
            
                release_altitude=data["release_altitude"] or None,
                tow_cost_actual=parse_money(data["tow_cost"]),
                rental_cost_actual=parse_money(data["flight_cost"]),
                field=data["field"],
                notes="",
            )

            flight.launch_method = infer_launch_method(data["towpilot"])
            flight.save()

        print(f"\n✅ Imported {count} flights.")


def parse_money(val):
    if not val:
        return None
    try:
        return Decimal(str(val).replace("$", "").replace(",", ""))
    except:
        return None


def infer_launch_method(towpilot_name):
    if not towpilot_name:
        return "tow"
    towpilot_name = towpilot_name.lower()
    if "winch" in towpilot_name:
        return "winch"
    elif "self-launch" in towpilot_name:
        return "self"
    elif "other" in towpilot_name:
        return "other"
    else:
        return "tow"
