import logging
import re
from datetime import datetime

import psycopg2
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils.timezone import make_aware

from members.models import Member

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

STATUS_MAP = {
    "M": "Full Member",
    "U": "Student Member",
    "Q": "Family Member",
    "F": "Charter Member",
    "H": "Honorary Member",
    "E": "Introductory Member",
    "I": "Inactive",
    "N": "Non-Member",
    "P": "Probationary Member",
    "T": "Transient Member",
    "A": "FAST Member",
    "S": "Service Member",
}

RATING_MAP = {
    "CFIG": "commercial",
    "CPL": "commercial",
    "PPL": "private",
    "S": "student",
    "F": "none",
    "N/A": "none",
}

US_STATE_ABBREVIATIONS = {
    "AL",
    "AK",
    "AZ",
    "AR",
    "CA",
    "CO",
    "CT",
    "DE",
    "FL",
    "GA",
    "HI",
    "ID",
    "IL",
    "IN",
    "IA",
    "KS",
    "KY",
    "LA",
    "ME",
    "MD",
    "MA",
    "MI",
    "MN",
    "MS",
    "MO",
    "MT",
    "NE",
    "NV",
    "NH",
    "NJ",
    "NM",
    "NY",
    "NC",
    "ND",
    "OH",
    "OK",
    "OR",
    "PA",
    "RI",
    "SC",
    "SD",
    "TN",
    "TX",
    "UT",
    "VT",
    "VA",
    "WA",
    "WV",
    "WI",
    "WY",
}


def parse_date(legacy_str):
    if not legacy_str:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%B %d, %Y", "%b %d, %Y", "%m/%Y"):
        try:
            return datetime.strptime(legacy_str.strip(), fmt)
        except Exception:
            continue
    return None


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


def extract_nickname(first_name):
    match = re.search(r'"(.*?)"', first_name)
    if match:
        nickname = match.group(1)
        first_name_clean = re.sub(r'".*?"', "", first_name).strip()
        return first_name_clean, nickname
    return first_name, ""


def generate_username(first, last, nickname):
    # Prefer nickname if available
    if nickname:
        first_part = re.sub(r"[^A-Za-z]", "", nickname)
    else:
        first_part = re.sub(r"[^A-Za-z]", "", first)

    last_part = re.sub(r"[^A-Za-z]", "", last)
    base = f"{first_part.lower()}.{last_part.lower()}"
    username = base
    suffix = 1
    while Member.objects.filter(username=username).exists():
        username = f"{base}{suffix}"
        suffix += 1
    return username


class Command(BaseCommand):
    help = (
        "Import legacy members from the SQL_ASCII database via psycopg2 "
        "using settings.DATABASES['legacy']"
    )

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
            cursor.execute("SELECT * FROM members")
            # psycopg2 cursor.description yields a sequence of 7-item tuples
            # where the first element is the column name. Accessing .name
            # on the tuple is incorrect and flagged by static analyzers.
            if cursor.description is None:
                columns = []
            else:
                columns = [desc[0] for desc in cursor.description]
            rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

        imported = 0

        for row in rows:
            handle = row["handle"].strip()
            raw_first = sanitize(row["firstname"]).strip()
            last = sanitize(row["lastname"]).strip()
            first, nickname = extract_nickname(raw_first)

            username = generate_username(first, last, nickname)

            member = Member.objects.filter(legacy_username=handle).first()
            if member is None:
                member = Member(legacy_username=handle, username=username)

            nickname_match = re.search(r'"([^"]+)"', first)
            nickname = nickname_match.group(1) if nickname_match else None
            first_cleaned = re.sub(r'"[^"]+"', "", first).strip()

            # Use the cleaned names for the object
            member.first_name = sanitize(first_cleaned)
            member.nickname = nickname
            member.username = generate_username(first_cleaned, last, nickname)
            member.last_name = last

            member.middle_initial = sanitize(row.get("middleinitial"))
            member.name_suffix = sanitize(row.get("namesuffix"))
            member.email = sanitize(row.get("email"))
            member.mobile_phone = sanitize(row.get("cell_phone"))
            member.phone = sanitize(row.get("phone1"))
            addr1 = sanitize(row.get("address1"))
            addr2 = sanitize(row.get("address2"))
            member.address = f"{addr1} {addr2}".strip()
            member.city = sanitize(row.get("city"))
            state_raw = sanitize(row.get("state")).upper()
            if state_raw in US_STATE_ABBREVIATIONS:
                member.state_code = state_raw
                member.state_freeform = ""
            else:
                member.state_code = ""
                member.state_freeform = sanitize(row.get("state"))
            member.zip_code = sanitize(row.get("zip"))
            member.emergency_contact = sanitize(row.get("emergency_contact"))
            ssa = row.get("ssa_id")
            member.SSA_member_number = ssa if ssa else None
            official_title = sanitize(row.get("official_title"))
            private_notes = sanitize(row.get("private_notes"))

            # Check if "Deceased" appears in either field
            if (
                "deceased" in official_title.lower()
                or "deceased" in private_notes.lower()
            ):
                member.membership_status = "Deceased"
            else:
                status_value = row.get("memberstatus")
                member.membership_status = STATUS_MAP.get(
                    str(status_value) if status_value is not None else "",
                    "Non-Member",
                )

            # Only activate if the member deserves it
            # If this person is inactive, or not a member or
            # pending, or dead, don't let them log into the site.
            # since settings.py entry has AUTH_USER_MODEL = 'members.Member'
            # this is where we set if the user is active or not.
            if member.membership_status not in (
                "Inactive",
                "Non-Member",
                "Pending",
                "Deceased",
            ):
                member.is_active = True
            else:
                member.is_active = False

            rating_key = row.get("rating")
            member.glider_rating = RATING_MAP.get(
                str(rating_key) if rating_key is not None else "", "student"
            )
            member.director = row.get("director")
            member.treasurer = row.get("treasurer")
            member.secretary = row.get("secretary")
            member.webmaster = row.get("webmaster")
            member.instructor = row.get("instructor")
            member.towpilot = row.get("towpilot")
            member.duty_officer = row.get("dutyofficer")
            member.assistant_duty_officer = row.get("ado")
            row.get("private_notes")
            # debug: raw_notes repr truncated for brevity

            member.public_notes = sanitize(row.get("public_notes"))
            member.private_notes = sanitize(row.get("private_notes"))
            # debug: private_notes sanitized

            join_date = parse_date(row.get("joindate"))
            if not join_date:
                try:
                    lastupdated = row.get("lastupdated")
                    if lastupdated is None:
                        raise ValueError("no lastupdated value")
                    join_date = datetime.fromtimestamp(int(lastupdated))
                except Exception:
                    join_date = datetime(2000, 1, 1)
            member.joined_club = make_aware(join_date)

            deceased_keywords = ["deceased"]
            title_text = row.get("official_title") or ""
            private_text = row.get("private_notes") or ""
            death_note = (f"{title_text}{private_text}").lower()

            if any(word in death_note for word in deceased_keywords):
                member.membership_status = "Deceased"

            member.is_active = member.membership_status not in [
                "Inactive",
                "Non-Member",
                "Pending",
                "Deceased",
            ]

            if dry_run:
                msg = "[DRY RUN] Would import: {} {} ({})".format(
                    first, last, username
                )
                self.stdout.write(msg)
            else:
                member.save()
                msg = "Imported: {} {} ({})".format(
                    first, last, username
                )
                self.stdout.write(msg)
            imported += 1

        self.stdout.write(
            self.style.SUCCESS(
                "Import complete. Total imported: {}".format(imported)
            )
        )
