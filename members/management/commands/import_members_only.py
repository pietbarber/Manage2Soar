import logging
from datetime import datetime

import psycopg2
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils.timezone import make_aware
from members.models import Member
from django.db.models import Q

logger = logging.getLogger(__name__)

STATUS_MAP = {
    'M': 'active',
    'U': 'student',
    'Q': 'family',
    'F': 'founding',
    'H': 'honorary',
    'E': 'intro',
    'C': 'ssef',
    'I': 'inactive',
    'N': 'nonmember',
    'P': 'probationary',
    'T': 'transient',
    'A': 'fast',
    'S': 'service',
}

RATING_MAP = {
    'CFIG': 'commercial',
    'CPL': 'commercial',
    'PPL': 'private',
    'S': 'student',
    'F': 'none',
    'N/A': 'none',
}

US_STATE_ABBREVIATIONS = {
    'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA', 'HI', 'ID',
    'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD', 'MA', 'MI', 'MN', 'MS',
    'MO', 'MT', 'NE', 'NV', 'NH', 'NJ', 'NM', 'NY', 'NC', 'ND', 'OH', 'OK',
    'OR', 'PA', 'RI', 'SC', 'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV',
    'WI', 'WY'
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
        return ''
    try:
        cleaned = text.encode('cp1252', errors='ignore').decode('utf-8', errors='ignore')
        return cleaned.replace('\r', '').strip()
    except Exception as e:
        logger.warning(f"Failed to sanitize text: {e}")
        return ''

def generate_username(first, last):
    base = f"{first.lower()}.{last.lower()}"
    username = base
    suffix = 1
    while Member.objects.filter(username=username).exists():
        username = f"{base}{suffix}"
        suffix += 1
    return username

class Command(BaseCommand):
    help = "Import legacy members from the SQL_ASCII database using psycopg2 via settings.DATABASES['legacy']"

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Run without saving changes')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        self.stdout.write(self.style.NOTICE("Connecting to legacy database via settings.DATABASES['legacy']..."))

        legacy = settings.DATABASES['legacy']
        conn = psycopg2.connect(
            dbname=legacy['NAME'],
            user=legacy['USER'],
            password=legacy['PASSWORD'],
            host=legacy.get('HOST', ''),
            port=legacy.get('PORT', ''),
        )
        conn.set_client_encoding('WIN1252')

        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM members")
            columns = [desc.name for desc in cursor.description]
            rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

        imported = 0

        for row in rows:
            handle = row['handle'].strip()
            first = sanitize(row['firstname']).strip()
            last = sanitize(row['lastname']).strip()

            username = generate_username(first, last)

            member = Member.objects.filter(legacy_username=handle).first() or Member(
                legacy_username=handle, username=username
            )

            member.username = member.username or username
            member.first_name = first
            member.last_name = last
            member.middle_initial = sanitize(row.get('middleinitial'))
            member.name_suffix = sanitize(row.get('namesuffix'))
            member.email = sanitize(row.get('email'))
            member.mobile_phone = sanitize(row.get('cell_phone'))
            member.phone = sanitize(row.get('phone1'))
            member.address = f"{sanitize(row.get('address1'))} {sanitize(row.get('address2'))}".strip()
            member.city = sanitize(row.get('city'))
            state_raw = sanitize(row.get('state')).upper()
            if state_raw in US_STATE_ABBREVIATIONS:
                member.state_code = state_raw
                member.state_freeform = ''
            else:
                member.state_code = ''
                member.state_freeform = sanitize(row.get('state'))
            member.zip_code = sanitize(row.get('zip'))
            member.emergency_contact = sanitize(row.get('emergency_contact'))
            ssa = row.get('ssa_id')
            member.SSA_member_number = ssa if ssa else None
            member.membership_status = STATUS_MAP.get(row.get('memberstatus'), 'nonmember')
            member.glider_rating = RATING_MAP.get(row.get('rating'), 'student')
            member.director = row.get('director')
            member.treasurer = row.get('treasurer')
            member.secretary = row.get('secretary')
            member.webmaster = row.get('webmaster')
            member.instructor = row.get('instructor')
            member.towpilot = row.get('towpilot')
            member.duty_officer = row.get('dutyofficer')
            member.assistant_duty_officer = row.get('ado')

            public_notes = sanitize(row.get('public_notes'))
            private_notes = sanitize(row.get('private_notes'))
            logger.debug(f"{handle} private_notes length after sanitize: {len(private_notes)}")
            member.notes = f"{public_notes}\n---\n{private_notes}".strip()

            join_date = parse_date(row.get('joindate'))
            if not join_date:
                try:
                    join_date = datetime.fromtimestamp(int(row.get('lastupdated')))
                except Exception:
                    join_date = datetime(2000, 1, 1)
            member.date_joined = make_aware(join_date)

            if dry_run:
                self.stdout.write(f"[DRY RUN] Would import: {first} {last} ({username})")
            else:
                member.save()
                self.stdout.write(f"Imported: {first} {last} ({username})")
            imported += 1

        self.stdout.write(self.style.SUCCESS(f"Import complete. Total imported: {imported}"))