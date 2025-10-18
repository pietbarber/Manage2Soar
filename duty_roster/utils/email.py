from django.conf import settings
from django.core.mail import send_mail


def notify_ops_status(assignment):
    print(
        (
            f"🧠 State: tow_pilot={assignment.tow_pilot}, "
            f"duty_officer={assignment.duty_officer}, "
            f"confirmed={assignment.is_confirmed}"
        )
    )

    if not assignment or assignment.is_scheduled:
        return  # Ignore scheduled days

    ops_date = assignment.date.strftime("%A, %B %d, %Y")
    subject_prefix = "[Manage2Soar]"

    from siteconfig.utils import get_role_title

    # 1. Ad-hoc day created (no crew yet)
    if not assignment.tow_pilot and not assignment.duty_officer:
        tow_title = get_role_title("towpilot") or "Tow Pilot"
        do_title = get_role_title("duty_officer") or "Duty Officer"
        calendar_url = f"{settings.SITE_URL}/duty_roster/calendar/"
        subj = f"{subject_prefix} Ad-Hoc Operations Proposed for {ops_date}"
        msg = (
            f"An ad-hoc ops day has been proposed for {ops_date}.\n\n"
            f"{tow_title}s and {do_title.lower()}s needed!\n\n"
            f"Calendar: {calendar_url}"
        )
        send_mail(
            subject=subj,
            message=msg,
            from_email="noreply@default.manage2soar.com",
            recipient_list=[
                "instructors@default.manage2soar.com",
                "towpilots@default.manage2soar.com",
            ],
        )
        return

    # 2. Ad-hoc ops day now confirmed
    if assignment.tow_pilot and assignment.duty_officer and not assignment.is_scheduled:
        if not assignment.is_confirmed:
            print("📣 Minimum crew present — confirming ops")
            assignment.is_confirmed = True
            assignment.save()

            tow_title = get_role_title("towpilot") or "Tow Pilot"
            do_title = get_role_title("duty_officer") or "Duty Officer"
            calendar_url = f"{settings.SITE_URL}/duty_roster/calendar/"
            subj = f"{subject_prefix} Ad-Hoc Ops Confirmed for {ops_date}"
            msg = (
                f"We now have a {tow_title.lower()} and {do_title.lower()} "
                f"for {ops_date}  operations are a go!\n\n"
                f"Calendar: {calendar_url}"
            )
            send_mail(
                subject=subj,
                message=msg,
                from_email="noreply@default.manage2soar.com",
                recipient_list=["members@default.manage2soar.com"],
            )
