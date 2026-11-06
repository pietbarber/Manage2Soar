from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from members.parity import build_authorization_snapshot, snapshot_json


class Command(BaseCommand):
    help = "Capture a read-only authorization and recipient parity snapshot."

    def add_arguments(self, parser):
        parser.add_argument("output", type=Path)
        parser.add_argument(
            "--include-emails",
            action="store_true",
            help="Include plaintext mailing-list recipients; hashes are used by default.",
        )
        parser.add_argument(
            "--legacy-compatible",
            action="store_true",
            help=(
                "Capture only the pre-0034 authorization/recipient projection; "
                "do not query role metadata or assignments."
            ),
        )

    def handle(self, *args, **options):
        output = options["output"]
        if output.exists():
            raise CommandError(f"Refusing to overwrite existing snapshot: {output}")
        snapshot = build_authorization_snapshot(
            include_emails=options["include_emails"],
            legacy_compatible=options["legacy_compatible"],
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        try:
            with output.open("x", encoding="utf-8") as stream:
                stream.write(snapshot_json(snapshot))
        except FileExistsError as exc:
            raise CommandError(
                f"Refusing to overwrite existing snapshot: {output}"
            ) from exc
        self.stdout.write(
            self.style.SUCCESS(
                f"{len(snapshot['legacy']['authorization']['members'])} members, "
                f"{len(snapshot.get('branch', {}).get('roles', []))} branch roles, and "
                f"{len(snapshot['legacy']['recipients'])} mailing lists to {output}"
            )
        )
