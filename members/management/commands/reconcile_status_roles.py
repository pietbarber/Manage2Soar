"""Reconcile explicit membership-status role mappings."""

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from members.models import Member
from members.services.status_role_reconciliation import apply
from siteconfig.models import MembershipStatus


class Command(BaseCommand):
    help = (
        "Report or apply explicit membership-status role mappings. "
        "The default is a read-only dry run."
    )

    def add_arguments(self, parser):
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument(
            "--apply",
            action="store_true",
            help="Apply safe changes; without this flag only report the plan.",
        )
        mode.add_argument(
            "--dry-run",
            action="store_true",
            help="Explicitly request the default read-only report mode.",
        )
        parser.add_argument(
            "--status-key",
            help="Limit reconciliation to members of one immutable status key.",
        )
        parser.add_argument(
            "--member-id",
            action="append",
            type=int,
            dest="member_ids",
            help="Limit reconciliation to a member ID; may be repeated.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            help="Process at most this many members in primary-key order.",
        )
        parser.add_argument(
            "--after-member-id",
            type=int,
            help="Resume after this member ID (exclusive).",
        )
        parser.add_argument(
            "--checkpoint-file",
            help="Write a JSON checkpoint after each processed member.",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            dest="as_json",
            help="Emit one machine-readable JSON report.",
        )

    def handle(self, *args, **options):
        status_key = options.get("status_key")
        member_ids = options.get("member_ids")
        limit = options.get("limit")
        after_member_id = options.get("after_member_id")
        checkpoint_file = options.get("checkpoint_file")
        if limit is not None and limit < 1:
            raise CommandError("--limit must be greater than zero.")
        if after_member_id is not None and after_member_id < 0:
            raise CommandError("--after-member-id must not be negative.")

        status = None
        if status_key:
            status = MembershipStatus.objects.filter(key=status_key).first()
            if status is None:
                raise CommandError(f"Unknown membership status key: {status_key}")

        members = Member.objects.order_by("pk")
        if status is not None:
            members = members.filter(membership_status=status.name)
        if member_ids is not None:
            members = members.filter(pk__in=member_ids)
        if after_member_id is not None:
            members = members.filter(pk__gt=after_member_id)
        if limit is not None:
            members = members[:limit]

        dry_run = not options["apply"]
        report = {
            "mode": "dry-run" if dry_run else "apply",
            "members": 0,
            "planned_grants": 0,
            "planned_revokes": 0,
            "ambiguous_members": 0,
            "unexplained_members": 0,
            "changes": [],
            "issues": [],
            "last_member_id": after_member_id,
            "complete": False,
        }

        checkpoint_path = Path(checkpoint_file) if checkpoint_file else None

        def write_checkpoint():
            if checkpoint_path is None:
                return
            temporary_path = checkpoint_path.with_name(f".{checkpoint_path.name}.tmp")
            temporary_path.write_text(
                json.dumps(
                    {
                        "last_member_id": report["last_member_id"],
                        "mode": report["mode"],
                        "status_key": status_key,
                        "complete": report["complete"],
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            temporary_path.replace(checkpoint_path)

        for member in members:
            result = apply(member, dry_run=dry_run)
            current_plan = result.plan
            report["members"] += 1
            report["last_member_id"] = member.pk
            report["planned_grants"] += len(current_plan.grants)
            report["planned_revokes"] += len(current_plan.revokes)
            report["unexplained_members"] += bool(current_plan.unexplained_group_ids)
            if current_plan.issues:
                report["ambiguous_members"] += 1
                report["issues"].append(
                    {
                        "member_id": member.pk,
                        "username": member.username,
                        "issues": [
                            {"code": issue.code, "detail": issue.detail}
                            for issue in current_plan.issues
                        ],
                    }
                )
            if current_plan.changed:
                report["changes"].append(
                    {
                        "member_id": member.pk,
                        "username": member.username,
                        "status_key": current_plan.status_key,
                        "grants": [target.source_key for target in current_plan.grants],
                        "revokes": [
                            target.source_key for target in current_plan.revokes
                        ],
                    }
                )
            write_checkpoint()

        report["complete"] = True
        write_checkpoint()

        if options["as_json"]:
            self.stdout.write(json.dumps(report, sort_keys=True))
        else:
            self.stdout.write(
                f"{report['mode']}: {report['members']} members, "
                f"{report['planned_grants']} grants, "
                f"{report['planned_revokes']} revokes, "
                f"{report['ambiguous_members']} ambiguous, "
                f"{report['unexplained_members']} with unexplained memberships"
            )
            for issue in report["issues"]:
                self.stdout.write(
                    self.style.WARNING(
                        f"member #{issue['member_id']} ({issue['username']}): "
                        + "; ".join(
                            f"{item['code']}: {item['detail']}"
                            for item in issue["issues"]
                        )
                    )
                )

        if report["ambiguous_members"]:
            raise CommandError(
                "Status-role reconciliation found ambiguous members; no ambiguous changes were applied."
            )
