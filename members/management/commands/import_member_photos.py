import csv

from django.core.management.base import BaseCommand

from members.models import Member


class Command(BaseCommand):
    help = (
        "Import member profile photos from CSV. Assumes images are already "
        "in the correct media directory."
    )

    def handle(self, *args, **kwargs):
        with open("member_photos.csv", newline="") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                if row["profile_photo"]:
                    try:
                        m = Member.objects.get(username=row["username"])
                        m.profile_photo = row["profile_photo"]
                        m.save()
                        self.stdout.write(
                            self.style.SUCCESS("Set photo for {}".format(m.username))
                        )
                    except Member.DoesNotExist:
                        self.stdout.write(
                            self.style.WARNING(
                                "Member {} not found.".format(row["username"])
                            )
                        )
