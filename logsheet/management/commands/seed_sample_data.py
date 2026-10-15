"""Seed realistic sample data into the LOCAL dev database.

Creates:
- 24 Northern-Virginia members (22 men / 2 women) with a realistic mix of
  instructors, tow pilots, private-rated pilots, students, and a member
  manager ("membermeister").
- The club fleet: 2x SGS 2-33 trainers, 1x SGS 1-26, 2 tow planes
  (Pawnee + SuperCub), and 3 privately-owned gliders, with invented N numbers.
- Aero tow charge schemes on both tow planes (hookup fee + tiered pricing).
- Three seasons of weekend, April-November flights honoring the club's
  operating patterns (training duals, student solos, rated flights, SGS 1-26
  private-pilot-only flights, and long private XC soars). Student pilots may
  solo only after logging 40 duals; student-solo slots rolled before any
  student reaches that threshold become extra training duals.

Safety (defense in depth):
- **Dry-run by default**: without the ``--run`` flag the command only prints
  what it would do and exits — it writes nothing. You must explicitly pass
  ``--run`` to modify the database.
- **Localhost guard**: even with ``--run`` it refuses to proceed unless the
  default DB host is localhost/127.0.0.1 (or ``--i-meant-it`` is passed), so
  it cannot touch production by accident.
- Idempotent by default: it clears previously-seeded sample data (identified
  by the ``@email.invalid`` members and the fixed sample N numbers) and then
  regenerates. ``--skip-wipe`` appends instead.
- Runs inside a single transaction and leaves all flights UNFINALIZED, so no
  billing, maintenance, or email side effects are produced.

Usage:
    python manage.py seed_sample_data                # DRY RUN (prints only)
    python manage.py seed_sample_data --run          # wipe + regenerate
    python manage.py seed_sample_data --run --seed 42        # reproducible
    python manage.py seed_sample_data --run --skip-wipe      # append instead
    python manage.py seed_sample_data --run --members-only   # members + fleet only
"""

from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q
from django.test import override_settings

# --- Seeding configuration -------------------------------------------------

DEV_PASSWORD = "SoarDev-2026!"
EMAIL_DOMAIN = "email.invalid"

# Seasons to generate (year, last-inclusive-month). 2026 is partial (through Oct).
SEASONS = [(2024, 11), (2025, 11), (2026, 10)]
# Season opens in April (month 4).
SEASON_OPEN_MONTH = 4

AIRFIELD_ID = "KFRR"
AIRFIELD_NAME = "Front Royal - Warren County Airport"

# Roster: 24 members (22 men / 2 women).
# rating: none | student | private | commercial
MEMBER_ROSTER = [
    # -- Instructors (commercial) --
    (
        "Hank",
        "Whitfield",
        "M",
        "instructor",
        "commercial",
        "Front Royal",
        "22630",
        "703-555-0101",
    ),
    (
        "Dale",
        "Prescott",
        "M",
        "instructor",
        "commercial",
        "Warrenton",
        "22347",
        "703-555-0102",
    ),
    (
        "Marcus",
        "Bell",
        "M",
        "instructor",
        "commercial",
        "Winchester",
        "22601",
        "571-555-0103",
    ),
    (
        "Elaine",
        "Farrow",
        "F",
        "instructor",
        "commercial",
        "Stephens City",
        "22650",
        "571-555-0104",
    ),
    # -- Tow pilots (commercial) --
    ("Ray", "Danner", "M", "towpilot", "commercial", "Luray", "22634", "703-555-0105"),
    (
        "Tom",
        "Okafor",
        "M",
        "towpilot",
        "commercial",
        "Marshall",
        "22645",
        "703-555-0106",
    ),
    (
        "Sam",
        "Delgado",
        "M",
        "towpilot",
        "commercial",
        "Middletown",
        "22841",
        "571-555-0107",
    ),
    (
        "Greg",
        "Halloway",
        "M",
        "towpilot",
        "commercial",
        "Dumfries",
        "22026",
        "703-555-0108",
    ),
    (
        "Nick",
        "Sandoval",
        "M",
        "towpilot",
        "commercial",
        "Ashburn",
        "20146",
        "571-555-0109",
    ),
    (
        "Priya",
        "Nair",
        "F",
        "towpilot",
        "commercial",
        "Manassas",
        "20109",
        "571-555-0110",
    ),
    # -- Private-rated pilots --
    (
        "Owen",
        "Marsh",
        "M",
        "member_manager",
        "private",
        "Front Royal",
        "22630",
        "703-555-0111",
    ),
    ("Curtis", "Boone", "M", None, "private", "Gainesville", "22066", "703-555-0112"),
    ("Felix", "Grant", "M", None, "private", "Leesburg", "20175", "571-555-0113"),
    (
        "Andre",
        "Whitaker",
        "M",
        None,
        "private",
        "Fredericksburg",
        "22401",
        "703-555-0114",
    ),
    ("Paul", "Kowalski", "M", None, "private", "Warrenton", "22347", "703-555-0115"),
    ("Ted", "Bannister", "M", None, "private", "Culpeper", "22701", "571-555-0116"),
    ("Rob", "Ellery", "M", None, "private", "Winchester", "22601", "703-555-0117"),
    # -- Students --
    ("Cody", "Reyes", "M", None, "student", "Front Royal", "22630", "703-555-0118"),
    ("Tyler", "Vance", "M", None, "student", "Stephens City", "22650", "571-555-0119"),
    ("Josh", "Carver", "M", None, "student", "Luray", "22634", "703-555-0120"),
    ("Liam", "Foster", "M", None, "student", "Staunton", "24401", "703-555-0121"),
    ("Noah", "Pratt", "M", None, "student", "Winchester", "22601", "571-555-0122"),
    ("Ben", "Aldana", "M", None, "student", "Warrenton", "22347", "703-555-0123"),
    ("Kyle", "Duran", "M", None, "student", "Marshall", "22645", "703-555-0124"),
]

# Fleet: (make, model, n_number, club_owned, seats, rental_rate, owner_key)
GLIDERS = [
    ("Rolladen-Schneider", "SGS 2-33", "N2233A", True, 2, "40.00", None),
    ("Rolladen-Schneider", "SGS 2-33", "N2233B", True, 2, "40.00", None),
    ("Rolladen-Schneider", "SGS 1-26", "N126KS", True, 1, "25.00", None),
    ("Schempp-Hirth", "Discus", "N501XD", False, 1, None, "private"),
    ("Schleicher", "ASK 21", "N633LS", False, 2, None, "private"),
    ("Rolladen-Schneider", "LS-8", "N721AS", False, 1, None, "private"),
]

# Tow planes: (name, make, model, n_number)
TOWPLANES = [
    ("Pawnee", "Piper", "PA-25", "N424PW"),
    ("SuperCub", "Cessna", "185", "N185SC"),
]

SAMPLE_GLIDER_NNUMBERS = [g[2] for g in GLIDERS]
SAMPLE_TOWPLANE_NNUMBERS = [t[3] for t in TOWPLANES]

# Scenario weights for flights (sum to 100).
SCENARIOS = [
    # (weight, kind)
    (35, "dual"),
    (15, "student_solo"),
    (20, "rated_solo"),
    (10, "rated_passenger"),
    (10, "sgs126"),
    (10, "xc"),
]

# Training-dual release-altitude / duration (minutes) profile.
# (release_altitude_ft, duration_minutes, weight)
DUAL_TOWS = [
    (3000, 15, 60),
    (1500, 9, 30),
    (300, 2, 10),
]

# A student pilot may solo only after logging this many dual (training) flights.
# Student-solo slots rolled before any student has reached this threshold are
# converted into additional dual flights, so students train first, then solo.
STUDENT_SOLO_MIN_DUALS = 40


def _rand_time(start: time, end: time, rnd) -> time:
    """Random time-of-day between start and end (inclusive-ish)."""
    start_s = start.hour * 3600 + start.minute * 60
    end_s = end.hour * 3600 + end.minute * 60
    if end_s <= start_s:
        end_s += 86400
    chosen = start_s + rnd.randint(0, end_s - start_s)
    chosen %= 86400
    return time(chosen // 3600, (chosen % 3600) // 60)


def _duration_to_time(launch: time, minutes: int) -> time:
    base = datetime.combine(date(2024, 1, 1), launch) + timedelta(minutes=minutes)
    if base.hour >= 24:
        base = base.replace(hour=base.hour - 24)
    return base.time()


class Command(BaseCommand):
    help = (
        "Seed realistic sample members, aircraft, and 3 seasons of flights "
        "into the LOCAL dev database (localhost/127.0.0.1 only)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--run",
            action="store_true",
            help=(
                "REQUIRED to actually write data. Without this flag the command "
                "only prints what it would do and exits (dry-run)."
            ),
        )
        parser.add_argument(
            "--skip-wipe",
            action="store_true",
            help="Append instead of clearing previously-seeded sample data.",
        )
        parser.add_argument(
            "--members-only",
            action="store_true",
            help="Only seed members + fleet (skip flight generation).",
        )
        parser.add_argument(
            "--i-meant-it",
            action="store_true",
            help="Override the localhost-only safety guard (use with extreme care).",
        )
        parser.add_argument(
            "--seed",
            type=int,
            default=None,
            help="Optional RNG seed for reproducible flight data.",
        )

    def handle(self, *args, **options):
        # -- Dry-run guard: without --run, print what we'd do and exit. ------
        if not options["run"]:
            self.stdout.write(
                self.style.WARNING(
                    "\nThis command would seed the following data into the "
                    "database:\n"
                )
            )
            self.stdout.write(
                "  • 24 members (22 men / 2 women) — instructors, tow pilots,\n"
                "    private-rated pilots, students, 1 member manager\n"
            )
            self.stdout.write(
                "  • 6 gliders: 2× SGS 2-33, 1× SGS 1-26, 3 privately owned\n"
            )
            self.stdout.write("  • 2 tow planes: Pawnee + SuperCub\n")
            self.stdout.write("  • Aero tow charge schemes on both tow planes\n")
            self.stdout.write(
                "  • 3 seasons (2024, 2025, 2026→Oct) of weekend flights\n"
            )
            self.stdout.write(
                "  • All flights left UNFINALIZED (no billing/maintenance)\n"
            )
            self.stdout.write(
                self.style.WARNING(
                    "\nThis is a DRY RUN. No data was written.\n"
                    "To actually seed the database, re-run with --run:\n"
                    f"  python manage.py seed_sample_data --run\n"
                    f"  python manage.py seed_sample_data --run --seed 42   "
                    f"# reproducible\n"
                    f"  python manage.py seed_sample_data --run --members-only\n"
                )
            )
            return

        import random

        rnd = random.Random(options["seed"])

        self._safety_guard(options)

        # Imports are deferred so module import stays cheap and so Django is
        # fully set up before touching models.
        from logsheet.models import (
            Airfield,
            Flight,
            Glider,
            Logsheet,
            Towplane,
            TowplaneChargeScheme,
            TowplaneChargeTier,
        )
        from siteconfig.models import MembershipStatus

        # Wrap the entire operation in one transaction: any failure (including
        # a ProtectedError during the wipe) rolls everything back cleanly.
        with transaction.atomic():
            if not options["skip_wipe"]:
                self._wipe(Flight, Glider, Towplane)

            airfield = Airfield.objects.get_or_create(
                identifier=AIRFIELD_ID, defaults={"name": AIRFIELD_NAME}
            )[0]

            # Ensure the membership statuses we rely on exist and are active,
            # so Member.save() derives is_active=True for the seeded members.
            self._ensure_status(MembershipStatus, "Full Member")
            self._ensure_status(MembershipStatus, "Student Member")

            members = self._seed_members()

            glider_map, tow_map = self._seed_fleet(
                Glider, Towplane, TowplaneChargeScheme, TowplaneChargeTier, members
            )

            summary = {
                "members": len(members),
                "gliders": len(
                    Glider.objects.filter(n_number__in=SAMPLE_GLIDER_NNUMBERS)
                ),
                "towplanes": len(
                    Towplane.objects.filter(n_number__in=SAMPLE_TOWPLANE_NNUMBERS)
                ),
            }

            if not options["members_only"]:
                flight_counts = self._seed_flights(
                    rnd,
                    Flight,
                    Logsheet,
                    members,
                    glider_map,
                    tow_map,
                    airfield,
                )
                summary["flights"] = flight_counts

            self.stdout.write(self.style.SUCCESS("\n--- Seed summary ---"))
            for key, value in summary.items():
                self.stdout.write(f"  {key}: {value}")
            self.stdout.write(
                self.style.SUCCESS(
                    f"\nDone. Password for all sample members: {DEV_PASSWORD}"
                )
            )

    # ------------------------------------------------------------------
    # Safety guard
    # ------------------------------------------------------------------
    def _safety_guard(self, options):
        host = (settings.DATABASES.get("default", {}).get("HOST") or "").strip()
        allowed = {"localhost", "127.0.0.1", ""}
        if host not in allowed and not options["i_meant_it"]:
            self.stdout.write(
                self.style.ERROR(
                    f"\nABORT: refusing to seed against DB host '{host}'.\n"
                    "This command is intended for the LOCAL dev database only "
                    "(localhost/127.0.0.1).\n"
                    "If you truly intend to seed this database, re-run with "
                    "--i-meant-it.\n"
                )
            )
            raise SystemExit(1)
        self.stdout.write(self.style.WARNING(f"Target DB host: {host or '(default)'}"))

    # ------------------------------------------------------------------
    # Wipe (idempotency)
    # ------------------------------------------------------------------
    def _wipe(self, Flight, Glider, Towplane):
        from billing.models import Ledger, LedgerEntry
        from knowledgetest.models import WrittenTestAttempt
        from logsheet.models import (
            AircraftMeister,
            FlightSplitRequest,
            Logsheet,
            LogsheetGuestPayment,
            LogsheetTowplane,
            MaintenanceDeadline,
            MaintenanceIssue,
            TowplaneChargeScheme,
            TowplaneCloseout,
        )
        from members.models import EmergencyContact

        Member = get_user_model()

        seeded_member = Q(email__endswith=f"@{EMAIL_DOMAIN}")
        seeded_glider = Q(n_number__in=SAMPLE_GLIDER_NNUMBERS)
        seeded_tow = Q(n_number__in=SAMPLE_TOWPLANE_NNUMBERS)
        seeded_aircraft = seeded_glider | seeded_tow

        member_pks = list(
            Member.objects.filter(seeded_member).values_list("id", flat=True)
        )
        glider_pks = list(
            Glider.objects.filter(seeded_glider).values_list("id", flat=True)
        )
        tow_pks = list(Towplane.objects.filter(seeded_tow).values_list("id", flat=True))

        # Flights touching any seeded member or aircraft (regardless of airfield).
        flight_filter = Q()
        if member_pks:
            flight_filter |= (
                Q(pilot_id__in=member_pks)
                | Q(instructor_id__in=member_pks)
                | Q(passenger_id__in=member_pks)
                | Q(tow_pilot_id__in=member_pks)
            )
        if glider_pks:
            flight_filter |= Q(glider_id__in=glider_pks)
        if tow_pks:
            flight_filter |= Q(towplane_id__in=tow_pks)

        flights = (
            Flight.objects.filter(flight_filter)
            if (member_pks or glider_pks or tow_pks)
            else Flight.objects.none()
        )
        flight_count = flights.count()

        # Delete dependent rows that reference flights or aircraft (defensive;
        # these are empty in the normal unfinalized-seed scenario).
        if flight_count:
            FlightSplitRequest.objects.filter(
                flight_id__in=flights.values("id")
            ).delete()
            LogsheetGuestPayment.objects.filter(
                flight_id__in=flights.values("id")
            ).delete()
            MaintenanceIssue.objects.filter(
                Q(glider_id__in=glider_pks) | Q(towplane_id__in=tow_pks)
            ).delete()
            MaintenanceDeadline.objects.filter(
                Q(glider_id__in=glider_pks) | Q(towplane_id__in=tow_pks)
            ).delete()
        # Aircraft-scoped rows.
        TowplaneChargeScheme.objects.filter(towplane_id__in=tow_pks).delete()
        TowplaneCloseout.objects.filter(towplane_id__in=tow_pks).delete()
        LogsheetTowplane.objects.filter(towplane_id__in=tow_pks).delete()
        AircraftMeister.objects.filter(
            Q(glider_id__in=glider_pks) | Q(towplane_id__in=tow_pks)
        ).delete()
        # Member-scoped PROTECT references (defensive; normally empty for an
        # unfinalized seed).
        if member_pks:
            EmergencyContact.objects.filter(member_id__in=member_pks).delete()
            # Ledger (PROTECT on member) and its entries.
            ledgers = Ledger.objects.filter(member_id__in=member_pks)
            ledger_pks = list(ledgers.values_list("id", flat=True))
            if ledger_pks:
                LedgerEntry.objects.filter(ledger_id__in=ledger_pks).delete()
            ledgers.delete()
            WrittenTestAttempt.objects.filter(student_id__in=member_pks).delete()

        flights.delete()

        # Logsheets whose creator is a seeded member (their flights are gone now).
        if member_pks:
            Logsheet.objects.filter(created_by_id__in=member_pks).delete()

        # Now the aircraft (their charge schemes / closeouts already removed).
        Glider.objects.filter(seeded_glider).delete()
        Towplane.objects.filter(seeded_tow).delete()

        # Finally the members (PROTECT references above already cleared).
        member_q = Member.objects.filter(seeded_member)
        member_count = member_q.count()
        member_q.delete()
        self.stdout.write(
            self.style.WARNING(
                f"Wiped {member_count} member(s), {flight_count} flight(s); "
                f"{Glider.objects.count()} glider(s) and "
                f"{Towplane.objects.count()} towplane(s) remain after wipe."
            )
        )

    # ------------------------------------------------------------------
    # Membership status helper
    # ------------------------------------------------------------------
    def _ensure_status(self, MembershipStatus, name):
        status, created = MembershipStatus.objects.get_or_create(
            name=name, defaults={"is_active": True, "sort_order": 50}
        )
        if created or not status.is_active:
            status.is_active = True
            status.save()

    # ------------------------------------------------------------------
    # Members
    # ------------------------------------------------------------------
    def _seed_members(self):
        Member = get_user_model()
        members = {}
        # Skip avatar generation (writes an identicon per member to MEDIA_ROOT).
        with override_settings(TESTING=True):
            for (
                first,
                last,
                gender,
                role,
                rating,
                city,
                zip_code,
                phone,
            ) in MEMBER_ROSTER:
                email = f"{first.lower()}.{last.lower()}@{EMAIL_DOMAIN}"
                username = f"{first.lower()}.{last.lower()}"
                is_student = rating == "student"
                kwargs = {
                    "username": username,
                    "email": email,
                    "password": DEV_PASSWORD,
                    "first_name": first,
                    "last_name": last,
                    "phone": phone,
                    "city": city,
                    "state_code": "VA",
                    "zip_code": zip_code,
                    "country": "US",
                    "glider_rating": rating,
                    "membership_status": (
                        "Student Member" if is_student else "Full Member"
                    ),
                }
                if role == "instructor":
                    kwargs["instructor"] = True
                elif role == "towpilot":
                    kwargs["towpilot"] = True
                elif role == "member_manager":
                    kwargs["member_manager"] = True
                if rating in ("private", "commercial"):
                    kwargs["pilot_certificate_number"] = f"FAA-{username.upper()}"
                member = Member.objects.create_user(**kwargs)
                members[f"{first.lower()}.{last.lower()}"] = member
        self.stdout.write(self.style.SUCCESS(f"Seeded {len(members)} members."))
        return members

    # ------------------------------------------------------------------
    # Fleet
    # ------------------------------------------------------------------
    def _seed_fleet(self, Glider, Towplane, Scheme, Tier, members):
        glider_map = {}
        for make, model, n_number, club_owned, seats, rate, owner_key in GLIDERS:
            glider = Glider.objects.create(
                make=make,
                model=model,
                n_number=n_number,
                competition_number="",
                club_owned=club_owned,
                seats=seats,
                rental_rate=Decimal(rate) if rate else None,
                max_rental_rate=Decimal(rate) if rate else None,
                is_active=True,
            )
            if owner_key == "private":
                # Assign a private/commercial member as owner of this private glider.
                private_pilots = [
                    m
                    for m in members.values()
                    if m.glider_rating in ("private", "commercial")
                ]
                if private_pilots:
                    glider.owners.add(
                        private_pilots[len(glider_map) % len(private_pilots)]
                    )
            glider_map[n_number] = glider
        self.stdout.write(self.style.SUCCESS(f"Seeded {len(glider_map)} gliders."))

        tow_map = {}
        for name, make, model, n_number in TOWPLANES:
            tow = Towplane.objects.create(
                name=name,
                make=make,
                model=model,
                n_number=n_number,
                club_owned=True,
                is_active=True,
            )
            scheme, _ = Scheme.objects.update_or_create(
                towplane=tow,
                defaults={
                    "name": f"{name} Aero Tow Rates",
                    "hookup_fee": Decimal("25.00"),
                    "is_active": True,
                },
            )
            # Re-create tiers to be idempotent.
            scheme.charge_tiers.all().delete()
            Tier.objects.create(
                charge_scheme=scheme,
                altitude_start=0,
                altitude_end=1000,
                rate_type="flat",
                rate_amount=Decimal("0.00"),
                is_active=True,
            )
            Tier.objects.create(
                charge_scheme=scheme,
                altitude_start=1000,
                altitude_end=5000,
                rate_type="per_100ft",
                rate_amount=Decimal("1.00"),
                is_active=True,
            )
            tow_map[n_number] = tow
        self.stdout.write(
            self.style.SUCCESS(f"Seeded {len(tow_map)} tow planes + charge schemes.")
        )
        return glider_map, tow_map

    # ------------------------------------------------------------------
    # Flights
    # ------------------------------------------------------------------
    def _seed_flights(
        self, rnd, Flight, Logsheet, members, glider_map, tow_map, airfield
    ):
        members_by_key = members
        instructors = [m for m in members.values() if m.instructor]
        towpilots = [m for m in members.values() if m.towpilot]
        students = [m for m in members.values() if m.glider_rating == "student"]
        rated = [
            m for m in members.values() if m.glider_rating in ("private", "commercial")
        ]
        # Duty-officer pool: pilots rated at least private.
        duty_pool = rated
        manager = next(
            (m for m in members.values() if m.member_manager),
            members_by_key[next(iter(members_by_key))],
        )
        trainer_glider_keys = [g[2] for g in GLIDERS if g[1] == "SGS 2-33"]
        sgs126_key = next(g[2] for g in GLIDERS if g[1] == "SGS 1-26")
        private_glider_keys = [g[2] for g in GLIDERS if not g[3]]
        tow_keys = list(tow_map.keys())

        today = date.today()
        total_flights = 0
        logsheets_created = 0
        flights = []
        # Running per-student count of dual (training) flights logged so far.
        # Flights are generated in chronological order, so this reflects how many
        # duals each student has when a student-solo slot is rolled.
        dual_counts = {s.id: 0 for s in students}

        def make_flight(
            logsheet,
            launch,
            minutes,
            pilot,
            instructor,
            passenger,
            glider,
            towplane,
            tow_pilot,
            release_alt,
            flight_type,
        ):
            landing = _duration_to_time(launch, minutes)
            return Flight(
                logsheet=logsheet,
                launch_time=launch,
                landing_time=landing,
                duration=timedelta(minutes=minutes),
                pilot=pilot,
                instructor=instructor,
                passenger=passenger,
                glider=glider,
                towplane=towplane,
                tow_pilot=tow_pilot,
                airfield=airfield,
                release_altitude=release_alt,
                flight_type=flight_type,
                launch_method="tow",
                notes="",
                passenger_name="",
            )

        for year, last_month in SEASONS:
            month = SEASON_OPEN_MONTH
            while month <= last_month:
                day = 1
                # Find first weekend day of the month.
                while day <= 28:
                    d = date(year, month, day)
                    # Cap 2026 at today.
                    if d > today:
                        day = 29  # break inner
                        break
                    if d.weekday() in (5, 6):  # Saturday=5, Sunday=6
                        # ~8% of weekend days: no fly (weather).
                        if rnd.random() < 0.08:
                            day += 1
                            continue
                        logsheet = Logsheet.objects.create(
                            log_date=d,
                            airfield=airfield,
                            created_by=manager,
                            default_towplane=tow_map[tow_keys[0]],
                            duty_officer=rnd.choice(duty_pool),
                            tow_pilot=rnd.choice(towpilots),
                            finalized=False,
                        )
                        logsheets_created += 1

                        # Flight count: mostly ~15, sometimes fewer.
                        roll = rnd.random()
                        if roll < 0.70:
                            count = rnd.randint(13, 16)
                        elif roll < 0.90:
                            count = rnd.randint(8, 12)
                        else:
                            count = rnd.randint(1, 3)

                        for _ in range(count):
                            scenario = self._pick_scenario(rnd)
                            if scenario == "dual":
                                pilot = rnd.choice(students)
                                dual_counts[pilot.id] = dual_counts.get(pilot.id, 0) + 1
                                instructor = rnd.choice(instructors)
                                glider = glider_map[rnd.choice(trainer_glider_keys)]
                                alt, mins, _ = self._pick_dual(rnd)
                                flight = make_flight(
                                    logsheet,
                                    _rand_time(time(10, 0), time(16, 30), rnd),
                                    mins,
                                    pilot,
                                    instructor,
                                    None,
                                    glider,
                                    tow_map[rnd.choice(tow_keys)],
                                    rnd.choice(towpilots),
                                    alt,
                                    "dual",
                                )
                            elif scenario == "student_solo":
                                qualified = [
                                    s
                                    for s in students
                                    if dual_counts[s.id] >= STUDENT_SOLO_MIN_DUALS
                                ]
                                if qualified:
                                    pilot = rnd.choice(qualified)
                                    glider = glider_map[rnd.choice(trainer_glider_keys)]
                                    flight = make_flight(
                                        logsheet,
                                        _rand_time(time(10, 0), time(16, 45), rnd),
                                        15,
                                        pilot,
                                        None,
                                        None,
                                        glider,
                                        tow_map[rnd.choice(tow_keys)],
                                        rnd.choice(towpilots),
                                        3000,
                                        "solo",
                                    )
                                else:
                                    # No student has enough duals yet — this slot
                                    # becomes an extra training dual instead.
                                    pilot = rnd.choice(students)
                                    dual_counts[pilot.id] = (
                                        dual_counts.get(pilot.id, 0) + 1
                                    )
                                    instructor = rnd.choice(instructors)
                                    glider = glider_map[rnd.choice(trainer_glider_keys)]
                                    alt, mins, _ = self._pick_dual(rnd)
                                    flight = make_flight(
                                        logsheet,
                                        _rand_time(time(10, 0), time(16, 30), rnd),
                                        mins,
                                        pilot,
                                        instructor,
                                        None,
                                        glider,
                                        tow_map[rnd.choice(tow_keys)],
                                        rnd.choice(towpilots),
                                        alt,
                                        "dual",
                                    )
                            elif scenario == "rated_solo":
                                pilot = rnd.choice(rated)
                                glider = glider_map[rnd.choice(trainer_glider_keys)]
                                flight = make_flight(
                                    logsheet,
                                    _rand_time(time(10, 0), time(15, 30), rnd),
                                    rnd.randint(30, 75),
                                    pilot,
                                    None,
                                    None,
                                    glider,
                                    tow_map[rnd.choice(tow_keys)],
                                    rnd.choice(towpilots),
                                    3000,
                                    "solo",
                                )
                            elif scenario == "rated_passenger":
                                pilot = rnd.choice(rated)
                                others = [m for m in rated if m != pilot]
                                passenger = rnd.choice(others) if others else None
                                glider = glider_map[rnd.choice(trainer_glider_keys)]
                                flight = make_flight(
                                    logsheet,
                                    _rand_time(time(10, 0), time(15, 0), rnd),
                                    rnd.randint(40, 90),
                                    pilot,
                                    None,
                                    passenger,
                                    glider,
                                    tow_map[rnd.choice(tow_keys)],
                                    rnd.choice(towpilots),
                                    3000,
                                    "passenger",
                                )
                            elif scenario == "sgs126":
                                # Only private/commercial pilots may fly the 1-26.
                                pilot = rnd.choice(rated)
                                flight = make_flight(
                                    logsheet,
                                    _rand_time(time(10, 0), time(16, 0), rnd),
                                    rnd.randint(30, 60),
                                    pilot,
                                    None,
                                    None,
                                    glider_map[sgs126_key],
                                    tow_map[rnd.choice(tow_keys)],
                                    rnd.choice(towpilots),
                                    3000,
                                    "solo",
                                )
                            else:  # xc
                                pilot = rnd.choice(rated)
                                glider = glider_map[rnd.choice(private_glider_keys)]
                                # Cap duration so a 14:00 launch still lands by 17:00.
                                flight = make_flight(
                                    logsheet,
                                    _rand_time(time(12, 30), time(14, 0), rnd),
                                    rnd.randint(150, 180),
                                    pilot,
                                    None,
                                    None,
                                    glider,
                                    tow_map[rnd.choice(tow_keys)],
                                    rnd.choice(towpilots),
                                    3000,
                                    "solo",
                                )
                            flights.append(flight)

                    day += 1
                month += 1

        # bulk_create bypasses Model.save() and post_save signals, so no
        # instructor-Notification side effects are produced.
        if flights:
            Flight.objects.bulk_create(flights, batch_size=500)
        total_flights = len(flights)
        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {logsheets_created} logsheets with {total_flights} flights."
            )
        )
        return total_flights

    def _pick_scenario(self, rnd):
        total = sum(w for w, _ in SCENARIOS)
        r = rnd.randint(1, total)
        acc = 0
        for w, kind in SCENARIOS:
            acc += w
            if r <= acc:
                return kind
        return SCENARIOS[-1][1]

    def _pick_dual(self, rnd):
        total = sum(w for _, _, w in DUAL_TOWS)
        r = rnd.randint(1, total)
        acc = 0
        for alt, mins, w in DUAL_TOWS:
            acc += w
            if r <= acc:
                return alt, mins, w
        return DUAL_TOWS[-1]
