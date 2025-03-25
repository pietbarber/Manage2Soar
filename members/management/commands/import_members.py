import json
import os
from datetime import datetime
from django.core.management.base import BaseCommand, CommandError
from members.models import Member
from django.utils.dateparse import parse_date
from dateutil import parser as date_parser
from django.db import IntegrityError
from dateutil import parser
import re
import logging

class Command(BaseCommand):
    help = "Import members from a legacy JSON file."

    def add_arguments(self, parser):
        parser.add_argument("json_file", type=str, help="Path to the legacy members JSON file.")
        parser.add_argument(
            "--commit", action="store_true", help="Save changes to the database. Without this, only previews are shown."
        )

    def handle(self, *args, **options):
        json_path = options["json_file"]
        commit = options["commit"]

        if not os.path.exists(json_path):
            raise CommandError(f"File not found: {json_path}")

        with open(json_path, "r", encoding="utf-8") as f:
            try:
                members = json.load(f)
            except json.JSONDecodeError as e:
                raise CommandError(f"Invalid JSON: {e}")

        imported = 0
        skipped = 0

        for record in members:
            legacy_username = record.get("handle", "").strip()
            if not legacy_username:
                self.stdout.write(self.style.WARNING("Skipping record with no 'handle'."))
                skipped += 1
                continue

            # Parse and normalize fields
            email = record.get("email", "").strip().lower() or None
            first_name = record.get("firstname", "").strip().title()
            last_name = record.get("lastname", "").strip().title()

            join_raw = record.get("joindate", "")
            join_date = self.parse_legacy_date(join_raw)

            try:
                member = Member(
                    username=legacy_username,
                    legacy_username=legacy_username,
                    first_name=first_name,
                    last_name=last_name,
                    email=email,
                    SSA_member_number=record.get("ssa_id") or None,
                    address=record.get("address1", ""),
                    city=record.get("city", ""),
                    state=record.get("state", ""),
                    zip_code=record.get("zip", ""),
                    phone=record.get("phone1", ""),
                    mobile_phone=record.get("cell_phone", ""),
                    glider_owned=record.get("glider_owned", ""),
                    second_glider_owned=record.get("glider_owned2", ""),
                    joined_club=join_date,
                    emergency_contact=record.get("emergency_contact", ""),
                    public_notes=record.get("public_notes", ""),
                    private_notes=record.get("private_notes", ""),
                    instructor=record.get("instructor", False),
                    duty_officer=record.get("dutyofficer", False),
                    assistant_duty_officer=record.get("ado", False),
                    secretary=record.get("secretary", False),
                    treasurer=record.get("treasurer", False),
                    webmaster=record.get("webmaster", False),
                    director=record.get("director", False),
                    is_active=True,
                )

                if commit:
                    member.save()
                self.stdout.write(f"{'✅ Imported' if commit else '👀 Preview'}: {member.username}")
                imported += 1

            except IntegrityError as e:
                self.stdout.write(self.style.WARNING(f"❌ IntegrityError for {legacy_username}: {e}"))
                skipped += 1
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"💥 Error with {legacy_username}: {e}"))
                skipped += 1

        self.stdout.write(self.style.SUCCESS(f"\nFinished. Imported: {imported}, Skipped: {skipped}"))


logger = logging.getLogger(__name__)

def parse_legacy_date(date_str):
    if not date_str or not date_str.strip():
        return None

    # Remove questionable characters like "?", "(est)", etc.
    clean_str = re.sub(r"[^\d\s/-]", "", date_str).strip()

    try:
        # Let dateutil do the heavy lifting
        return parser.parse(clean_str, default=None).date()
    except Exception:
        logger.warning(f"Unrecognized join date format: '{date_str}'")
        return None
