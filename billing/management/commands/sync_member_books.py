from django.core.management.base import BaseCommand, CommandError

from billing.ledger_services import (
    member_books_live,
    member_entries_missing_from_books,
    post_missing_member_entries,
)
from members.models import Member


class Command(BaseCommand):
    help = (
        "List member ledger entries missing from the club books (for example, "
        "ones posted while club books were turned off). Use --post to post them."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--post", action="store_true", help="Post the missing entries."
        )
        parser.add_argument(
            "--actor",
            help="Username recorded as creator of the postings (required with --post).",
        )

    def handle(self, *args, **options):
        if not member_books_live():
            raise CommandError("Club books aren't live; run Go-Live Setup first.")
        missing = list(member_entries_missing_from_books())
        for entry in missing:
            self.stdout.write(
                f"#{entry.pk} {entry.effective_date} {entry.ledger.member} "
                f"{entry.get_kind_display()} {entry.signed_amount}"
            )
        if not options["post"]:
            self.stdout.write(
                f"{len(missing)} entr(ies) missing. Dry run; nothing posted."
            )
            return
        if not options["actor"]:
            raise CommandError("--actor is required with --post.")
        try:
            actor = Member.objects.get(username=options["actor"])
        except Member.DoesNotExist as exc:
            raise CommandError(f"No member named {options['actor']}.") from exc
        posted = post_missing_member_entries(actor=actor)
        self.stdout.write(self.style.SUCCESS(f"Posted {posted} entr(ies)."))
