"""Read-only inventory of direct stats-export grants lacking source provenance."""

from django.contrib.auth.models import Permission
from django.core.management.base import BaseCommand

from members.models import Member


class Command(BaseCommand):
    help = "Report ambiguous direct stats-export grants; never changes permissions"

    def add_arguments(self, parser):
        parser.add_argument(
            "--include-member-ids",
            action="store_true",
            help="Include member IDs for an authorized, tenant-specific review",
        )

    def handle(self, *args, **options):
        permission = Permission.objects.filter(
            content_type__app_label="logsheet",
            content_type__model="logsheet",
            codename="can_export_stats_dump",
        ).first()
        if permission is None:
            self.stdout.write("No stats-export permission exists; no direct grants.")
            return

        direct = Member.objects.filter(user_permissions=permission).order_by("pk")
        for flag in (True, False):
            members = direct.filter(stats_monger=flag)
            self.stdout.write(f"stats_monger={flag}: {members.count()} direct grant(s)")
            if options["include_member_ids"]:
                self.stdout.write(
                    "member IDs: "
                    + ", ".join(str(pk) for pk in members.values_list("pk", flat=True))
                )
        self.stdout.write(
            "Direct grants have no source marker: the legacy flag cannot identify "
            "which rows are independent exceptions. Do not revoke without a "
            "reviewed tenant-specific list and a backup."
        )
