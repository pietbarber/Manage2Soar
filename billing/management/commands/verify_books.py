from django.core.management.base import BaseCommand, CommandError

from billing.ledger_services import verify_books


class Command(BaseCommand):
    help = "Check the club books for unbalanced entries and broken invariants."

    def handle(self, *args, **options):
        problems = verify_books()
        if problems:
            for problem in problems:
                self.stderr.write(problem)
            raise CommandError(f"{len(problems)} problem(s) found in the club books.")
        self.stdout.write(self.style.SUCCESS("Club books are in balance."))
