import csv

from django.core.management.base import BaseCommand

from members.models import Member


class Command(BaseCommand):
    help = "Export member usernames and profile photo paths to CSV."

    def handle(self, *args, **kwargs):
        with open("member_photos.csv", "w", newline="") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(["username", "profile_photo"])
            for m in Member.objects.all():
                writer.writerow(
                    [m.username, m.profile_photo.name if m.profile_photo else ""]
                )
        self.stdout.write(
            self.style.SUCCESS(
                "Exported member photo associations to member_photos.csv"
            )
        )
