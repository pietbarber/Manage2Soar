# logsheet/management/commands/import_legacy_flights.py

import logging
from datetime import time
from decimal import Decimal

import psycopg2
from django.conf import settings
from django.core.management.base import BaseCommand

from logsheet.models import Airfield, Flight, Glider, Logsheet
from logsheet.utils.aliases import resolve_towplane
from members.models import Member

# —————— configure a logger for this script ——————
logger = logging.getLogger("import_legacy_flights")
logger.setLevel(logging.INFO)
fh = logging.FileHandler("import_legacy_flights.log")
fh.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s %(levelname)s: %(message)s")
fh.setFormatter(formatter)
logger.addHandler(fh)


GLIDER_ALIASES = [
    {
        "legacy_name": "XZ",
        "start": "2000-01-02",
        "end": "2019-07-01",
        "n_number": "N27SN",
    },
    {
        "legacy_name": "XZ",
        "start": "2019-07-07",
        "end": "2099-12-31",
        "n_number": "N727AM",
    },
    {
        "legacy_name": "Russia",
        "start": "2000-01-02",
        "end": "2020-02-28",
        "n_number": "N912ES",
    },
    {
        "legacy_name": "Russia",
        "start": "2020-03-01",
        "end": "2099-12-31",
        "n_number": "N1051R",
    },
    {"legacy_name": "GROB 103", "n_number": "N4794E"},
    {"legacy_name": "SGS 1-36", "n_number": "N3617B"},
    {"legacy_name": "6E", "n_number": "N6108J"},
    {"legacy_name": "N341KS", "n_number": "N341KS"},
    {"legacy_name": "ASK-21", "n_number": "N341KS"},
    {"legacy_name": "N321K", "n_number": "N321K"},
    {"legacy_name": "N2671H", "n_number": "N2671H"},
    {"legacy_name": "CAPSTAN", "n_number": "N7475"},
    {"legacy_name": "Private", "n_number": "Unknown"},
    # Asked Bill Burner for its current whereabouts
    {"legacy_name": "Bergfalke", "n_number": "N9255X"},
    # This is Fred Winters old LS4 that he crashed, and no record of its N number
    {"legacy_name": "1FW", "n_number": "Unknown"},
    # Mike Peterson, contacted to get N number.
    {"legacy_name": "BG", "n_number": "Unknown"},
    # This may be the same glider as SF
    {"legacy_name": "PM", "n_number": "N8RX"},
    # Asked george Hazelrigg for its N number
    {"legacy_name": "9X", "n_number": "N270AS"},
    {"legacy_name": "Cirrus", "n_number": "N888AN"},
    {"legacy_name": "PW5", "n_number": "N505CC"},
    {"legacy_name": "H3", "n_number": "N16AL"},
    {"legacy_name": "9Y", "n_number": "N520RJ"},
    # Kevin Fleet's Libelle; Got it from Ginny Pawlak, she found his logbook
    {"legacy_name": "CI", "n_number": "N184W"},
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
    {"legacy_name": "517", "n_number": "N1137S"},
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
    {"legacy_name": "SM", "n_number": "N2671H"},
    {"legacy_name": "SG", "n_number": "D-KUHR"},
    {"legacy_name": "SZ", "n_number": "N483SZ"},
    {"legacy_name": "SGS 2-33", "n_number": "N2743H"},
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

    msg = (
        f"⚠️  Glider not resolved for legacy name '{legacy_name}' on "
        f"{flight_date}"
    )
    print(msg)
    return None


#########################################
#  find_member_by_name
#
# Try matching a name to legacy_username first,
# then fallback to first+last name.


def find_member_by_name(name):
    if not name:
        return None
    name = name.strip()

    # 0) direct username match
    user = Member.objects.filter(username__iexact=name).first()
    if user:
        return user

    # 1. Match legacy_username
    member = Member.objects.filter(legacy_username__iexact=name).first()
    if member:
        return member

    # 2. Fallback: match by first and last name
    parts = name.split()
    if len(parts) < 2:
        return None
    first, last = parts[0], parts[-1]
    return Member.objects.filter(
        first_name__iexact=first, last_name__iexact=last
    ).first()


class Command(BaseCommand):
    help = "Import legacy flights from PostgreSQL flight_info table"

    def add_arguments(self, parser):
        parser.add_argument(
            "--date",
            type=str,
            help="Only import flights on or after this date (YYYY-MM-DD)",
        )

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
            },
        )

        if created:
            self.stdout.write(self.style.SUCCESS("✅ Created import_bot user."))
        else:
            self.stdout.write(self.style.NOTICE("✔️ import_bot already exists."))

        import_user = Member.objects.filter(username="import_bot").first()
        print(import_user)

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

        # Handle --date argument
        date_arg = options.get("date")
        with conn.cursor() as cursor:
            if date_arg:
                self.stdout.write(
                    self.style.NOTICE(f"Importing flights on or after {date_arg}")
                )
                cursor.execute(
                    "SELECT * FROM flight_info2 "
                    "WHERE flight_date >= %s "
                    "ORDER BY flight_date ASC",
                    [date_arg],
                )
            else:
                cursor.execute("SELECT * FROM flight_info2 ORDER BY flight_date ASC")
            if cursor.description:
                columns = [col[0] for col in cursor.description]
                rows = cursor.fetchall()
            else:
                columns = []
                rows = []

        count = 0
        for row in rows:
            data = dict(zip(columns, row))
            towplane_name = data.get("towplane") or ""
            towplane_obj = None

            if towplane_name:
                towplane_obj = resolve_towplane(
                    data.get("towplane"), data.get("flight_date"), comment=""
                )
                if not towplane_obj:
                    print(
                        (
                            f"⚠️ No towplane matched for '{towplane_name}' "
                            f"on flight {data['flight_tracking_id']}"
                        )
                    )

            count += 1
            # print(
            #     (
            #         f"Importing flight #{data['flight_tracking_id']} on "
            #         f"{data['flight_date']}"
            #     )
            # )
            print(".", end="", flush=True)
            print(f" {data['flight_date']} ") if count % 100 == 0 else None

            # --- Resolve related objects ---
            pilot = find_member_by_name(data["pilot"])
            instructor = find_member_by_name(data["instructor"])
            passenger = find_member_by_name(data["passenger"])
            towpilot = find_member_by_name(data["towpilot"])

            # Glider by registration/N-number
            glider = resolve_glider(data["glider"], data["flight_date"])

            airfield = None
            unknown_airfields = set()

            field_raw = data.get("field")
            if not field_raw or not isinstance(field_raw, str):
                print(
                    (
                        f"⚠️ Missing or invalid field value: {field_raw!r} "
                        "— defaulting to KFRR"
                    )
                )
                airfield = Airfield.objects.get(identifier="KFRR")
            else:
                field_code = field_raw.strip().upper()
                try:
                    airfield = Airfield.objects.get(identifier=field_code)
                except Airfield.DoesNotExist:
                    print(
                        (
                            f"⚠️ Unknown airfield '{field_code}' (raw: '{field_raw}') "
                            "— defaulting to KFRR"
                        )
                    )
                    airfield = Airfield.objects.get(identifier="KFRR")
                    unknown_airfields.add(field_code)

            # Parse times
            def parse_time(t):
                return t if isinstance(t, time) else None

            logsheet, _ = Logsheet.objects.get_or_create(
                log_date=data["flight_date"],
                airfield=airfield,
                defaults={
                    "created_by": import_user,
                    "finalized": True,
                },
            )

            # --- Upsert the Flight so this import is idempotent ---
            # ensure we have parse_time, launch_time, landing_time, logsheet already
            defaults = {
                "airfield": airfield,
                "glider": resolve_glider(data["glider"], data["flight_date"]),
                "duration": None,
                "guest_pilot_name": data["pilot"] if not pilot else "",
                "legacy_pilot_name": data["pilot"] or "",
                "guest_instructor_name": data["instructor"] if not instructor else "",
                "legacy_instructor_name": data["instructor"] or "",
                "passenger": passenger,
                "passenger_name": data["passenger"] or "",
                "legacy_passenger_name": data["passenger"] or "",
                "tow_pilot": towpilot,
                "guest_towpilot_name": data["towpilot"] if not towpilot else "",
                "legacy_towpilot_name": data["towpilot"] or "",
                "towplane": towplane_obj,
                "release_altitude": data["release_altitude"] or None,
                "tow_cost_actual": parse_money(data["tow_cost"]),
                "rental_cost_actual": parse_money(data["flight_cost"]),
                "notes": "",
                "launch_method": infer_launch_method(data.get("towplane")),
            }

            flight, created = Flight.objects.update_or_create(
                logsheet=logsheet,
                pilot=pilot,
                instructor=instructor,
                glider=glider,
                towplane=towplane_obj,
                launch_time=parse_time(data["takeoff_time"]),
                landing_time=parse_time(data["landing_time"]),
                passenger=passenger,
                defaults=defaults,
            )
            if created:
                logger.info(
                    "➕ Created flight id=%s on %s", flight.id, data["flight_date"]
                )
            else:
                logger.info(
                    "♻️ Updated flight id=%s on %s", flight.id, data["flight_date"]
                )

        print(f"\n✅ Imported {count} flights.")
        print("⚠️ Unknown airfield codes encountered:", sorted(unknown_airfields))


def parse_money(val):
    if not val:
        return None
    try:
        return Decimal(str(val).replace("$", "").replace(",", ""))
    except Exception:
        # If parsing fails, return None. We intentionally swallow errors
        # for legacy data imports but could log when debugging.
        return None


def infer_launch_method(towplane_name):
    text = (towplane_name or "").strip().lower()
    if "winch" in text:
        return "winch"
    if "self" in text or "sl" in text:
        return "self"
    if "other" in text:
        return "other"
    return "tow"
