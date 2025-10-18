from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.utils.timezone import now

from duty_roster.models import DutyAssignment


class Command(BaseCommand):
    help = "Cancel unconfirmed ad-hoc ops days that are scheduled for tomorrow"

    def handle(self, *args, **kwargs):
        tomorrow = now().date() + timedelta(days=1)

        assignments = DutyAssignment.objects.filter(
            is_scheduled=False, is_confirmed=False, date=tomorrow
        )

        for assignment in assignments:
            ops_date = assignment.date.strftime("%A, %B %d, %Y")

            subject = "Ad-Hoc Ops Cancelled - {}".format(ops_date)
            message = (
                "Ad-hoc ops on {} could not get sufficient interest to ".format(
                    ops_date)
                + "meet the minimum duty crew of tow pilot and duty officer. The "
                + "deadline has passed and the ops have been cancelled for tomorrow.\n\n"
                + "Calendar: {}/duty_roster/calendar/".format(settings.SITE_URL)
            )
            send_mail(
                subject=subject,
                message=message,
                from_email="noreply@default.manage2soar.com",
                recipient_list=["members@default.manage2soar.com"],
            )

            self.stdout.write(
                self.style.WARNING(
                    f"Cancelled unconfirmed ad-hoc ops day for {assignment.date}"
                )
            )
            assignment.delete()
