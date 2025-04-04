import csv
import logging
from datetime import datetime

from django.core.management.base import BaseCommand
from django.db import connections, transaction
from members.models import Member

logger = logging.getLogger(__name__)

# Legacy mappings
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

# Attempt to parse a legacy join date

def parse_date(legacy_str):
    if not legacy_str:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%B %d, %Y", "%b %d, %Y", "%m/%Y"):
        try:
            return datetime.strptime(legacy_str.strip(), fmt).date()
        except Exception:
            continue
    return None

class Command(BaseCommand):
    help = "Import legacy members from the 'members' table into the Django Member model."

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Run without saving changes')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        self.stdout.write(self.style.NOTICE("Beginning import from legacy members table..."))

        with connections['default'].cursor() as cursor:
            cursor.execute("SELECT * FROM members")
            columns = [col[0] for col in cursor.description]
            rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

        imported, skipped = 0, 0
        
        for row in rows:
            handle = row['handle'].strip()
            first = row['firstname'].strip()
            last = row['lastname'].strip()

            member, created = Member.objects.get_or_create(legacy_username=handle)
            
            member.first_name = first
            member.last_name = last
            member.middle_initial = row['middleinitial'] or ""
            member.name_suffix = row['namesuffix'] or ""
            member.email = row['email'] or ""
            member.cell_phone = row['cell_phone'] or ""
            member.home_phone = row['phone1'] or ""
            member.address = f"{(row['address1'] or '').strip()} {(row['address2'] or '').strip()}".strip()
            member.city = row['city'] or ""
            member.state = row['state'] or ""
            member.zip_code = row['zip'] or ""
            member.emergency_contact = row['emergency_contact'] or ""
            member.ssa_number = row['ssa_id'] or 0
            member.membership_status = STATUS_MAP.get(row['memberstatus'], 'nonmember')
            member.pilot_rating = RATING_MAP.get(row['rating'], 'none')
            member.director = row['director'] == 't'
            member.treasurer = row['treasurer'] == 't'
            member.secretary = row['secretary'] == 't'
            member.webmaster = row['webmaster'] == 't'
            member.instructor = row['instructor'] == 't'
            member.towpilot = row['towpilot'] == 't'
            member.duty_officer = row['dutyofficer'] == 't'
            member.assistant_duty_officer = row['ado'] == 't'
            member.notes = (row['public_notes'] or "") + "\n---\n" + (row['private_notes'] or "")

            join_date = parse_date(row['joindate'])
            if not join_date:
                try:
                    join_date = datetime.fromtimestamp(int(row['lastupdated'])).date()
                except Exception:
                    join_date = datetime(2000, 1, 1).date()
            member.date_joined = join_date

            if dry_run:
                self.stdout.write(f"[DRY RUN] Would import: {first} {last} ({handle})")
            else:
                member.save()
                self.stdout.write(f"Imported: {first} {last} ({handle})")
            imported += 1

        self.stdout.write(self.style.SUCCESS(f"Import complete. Total imported: {imported}"))
