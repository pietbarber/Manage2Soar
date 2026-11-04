import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from members.parity import compare_authorization_snapshot_details


class Command(BaseCommand):
    help = "Compare two read-only authorization and recipient snapshots."

    def add_arguments(self, parser):
        parser.add_argument("before", type=Path)
        parser.add_argument("after", type=Path)
        parser.add_argument("--json", action="store_true", dest="as_json")

    def handle(self, *args, **options):
        try:
            before = json.loads(options["before"].read_text(encoding="utf-8"))
            after = json.loads(options["after"].read_text(encoding="utf-8"))
            details = compare_authorization_snapshot_details(before, after)
        except (
            OSError,
            json.JSONDecodeError,
            ValueError,
            TypeError,
            AttributeError,
        ) as exc:
            raise CommandError(str(exc)) from exc

        if options["as_json"]:
            self.stdout.write(json.dumps(details, indent=2, sort_keys=True))
        elif details["legacy_differences"]:
            for difference in details["legacy_differences"]:
                self.stdout.write(f"{difference['kind']}: {difference['path']}")
            self.stdout.write(
                self.style.WARNING(
                    f"{len(details['legacy_differences'])} stable legacy differences found"
                )
            )
        elif details["branch_differences"]:
            self.stdout.write(
                self.style.WARNING(
                    "Stable legacy parity unchanged; "
                    f"{len(details['branch_differences'])} branch-only differences "
                    "are informational and were not used for equality."
                )
            )
        else:
            message = "No stable legacy parity differences found"
            if details["schema_changed"]:
                message += "; schema/migration metadata changed"
            self.stdout.write(self.style.SUCCESS(message))
        if details["legacy_differences"]:
            raise CommandError(
                f"{len(details['legacy_differences'])} stable legacy parity differences found"
            )
