# members/management/commands/sync_sympa.py

import subprocess

from django.core.management.base import BaseCommand

from members.models import Member

# Map each Sympa list to a predicate on Member
SYMPA_LISTS = {
    "newsletter_sympa": lambda m: m.is_active_member,
    "instructors_sympa": lambda m: m.is_instructor,
    # …etc…
}


def get_current_sympa_members(listname):
    """
    Shell out to sympa.pl to get the list of subscribers.
    """
    proc = subprocess.run(
        ["/usr/bin/sympa.pl", "--list_member", listname],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    emails = set()
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Output is “address – status” if status != OK; split on whitespace
        emails.add(line.split()[0])
    return emails


def add_member(listname, email):
    subprocess.run(["/usr/bin/sympa.pl", "--add_member", listname, email], check=True)


def remove_member(listname, email):
    subprocess.run(
        ["/usr/bin/sympa.pl", "--remove_member", listname, email], check=True
    )


class Command(BaseCommand):
    help = "Sync Django members → Sympa subscriber lists"

    def handle(self, *args, **options):
        for listname, predicate in SYMPA_LISTS.items():
            msg = "Syncing Sympa list '{}'…".format(listname)
            self.stdout.write(msg)
            try:
                current = get_current_sympa_members(listname)
            except subprocess.CalledProcessError as e:
                err = "Failed to fetch members of {}: {}".format(listname, e)
                self.stderr.write(err)
                continue

            should_be = set(
                Member.objects.filter(predicate).values_list("email", flat=True)
            )
            to_add = should_be - current
            to_remove = current - should_be

            for email in sorted(to_add):
                try:
                    add_member(listname, email)
                    self.stdout.write(self.style.SUCCESS(" Added → " + email))
                except subprocess.CalledProcessError as e:
                    self.stderr.write(
                        "ERROR adding {} to {}: {}".format(email, listname, e))
            for email in sorted(to_remove):
                try:
                    remove_member(listname, email)
                    self.stdout.write(self.style.WARNING(" Removed → " + email))
                except subprocess.CalledProcessError as e:
                    self.stderr.write(
                        "ERROR removing {} from {}: {}".format(email, listname, e))

        self.stdout.write(self.style.SUCCESS("✓ Sympa sync complete."))
