# members/management/commands/import_members_from_legacy.py
import json
from datetime import datetime
from django.core.management.base import BaseCommand, CommandError
from members.models import Member
from django.db import transaction

# Legacy to modern field translations
RATING_MAP = {
    'S': 'student',
    'T': 'transition',
    'CPL': 'commercial',
    'PPL': 'private',
    'CFIG': 'commercial',
    'F': 'none',
    'N/A': 'none'
}

STATUS_MAP = {
    'M': 'Standard Member',
    'F': "Founding Member",
    'P': 'Probationary Member',
    'S': 'Student Member',
    'H': 'Honorary Member',
    'Q': 'Family Member',
    'T': 'Transient Member',
    'I': 'Inactive Member',
    'E': 'Introductory Member',
    'N': 'Non-Member'
    # Add more as needed
}

class Command(BaseCommand):
    help = "Import members from a legacy JSON dump"

    def add_arguments(self, parser):
        parser.add_argument('json_file', type=str, help='Path to legacy JSON file')
        parser.add_argument('--dry-run', action='store_true', help='Validate without writing to DB')

    def handle(self, *args, **options):
        json_file = options['json_file']
        dry_run = options['dry_run']

        try:
            with open(json_file, 'r') as f:
                members = json.load(f)
        except Exception as e:
            raise CommandError(f"Failed to load JSON: {e}")

        self.stdout.write(self.style.MIGRATE_HEADING(f"Loaded {len(members)} legacy members..."))

        errors = []
        valid_members = []

        for entry in members:
            try:
                member = Member(
                    legacy_username=entry['handle'],
                    first_name=entry.get('firstname', '')[:30],
                    last_name=entry.get('lastname', '')[:30],
                    email=entry.get('email') or None,
                    phone=entry.get('phone1') or None,
                    mobile_phone=entry.get('cell_phone') or None,
                    address=entry.get('address1') or '',
                    city=entry.get('city') or '',
                    state=entry.get('state') or '',
                    zip_code=entry.get('zip') or '',
                    glider_owned=entry.get('glider_owned') or '',
                    second_glider_owned=entry.get('glider_owned2') or '',
                    emergency_contact=entry.get('emergency_contact') or '',
                    glider_rating=RATING_MAP.get(entry.get('rating', '').strip().upper(), 'student'),
                    membership_status=STATUS_MAP.get(entry.get('memberstatus', '').strip().upper(), 'Non-Member'),
                    instructor=entry.get('instructor', False),
                    duty_officer=entry.get('dutyofficer', False),
                    assistant_duty_officer=entry.get('ado', False),
                    secretary=entry.get('secretary', False),
                    treasurer=entry.get('treasurer', False),
                    webmaster=entry.get('webmaster', False),
                    director=entry.get('director', False),
                    public_notes=entry.get('public_notes', ''),
                    private_notes=entry.get('private_notes', ''),
                )

                joindate = entry.get('joindate')
                if joindate:
                    try:
                        member.joined_club = datetime.strptime(joindate, '%Y-%m-%d').date()
                    except ValueError:
                        self.stdout.write(self.style.WARNING(f"Invalid joindate for {entry['handle']}: {joindate}"))

                valid_members.append(member)

            except Exception as e:
                errors.append((entry.get('handle', '?'), str(e)))

        if errors:
            self.stdout.write(self.style.NOTICE("Issues found during validation:"))
            for handle, err in errors:
                self.stdout.write(f" - {handle}: {err}")

            self.stdout.write(self.style.ERROR("Aborting due to validation errors."))
            return

        if dry_run:
            self.stdout.write(self.style.SUCCESS(f"Dry run completed. {len(valid_members)} valid entries found."))
        else:
            with transaction.atomic():
                for m in valid_members:
                    m.save()
            self.stdout.write(self.style.SUCCESS(f"Successfully imported {len(valid_members)} members."))
