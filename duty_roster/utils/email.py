from django.core.mail import send_mail
from django.conf import settings


def notify_ops_status(assignment):
    print(
        f"🧠 State: tow_pilot={assignment.tow_pilot}, duty_officer={assignment.duty_officer}, confirmed={assignment.is_confirmed}")

    if not assignment or assignment.is_scheduled:
        return  # Ignore scheduled days

    ops_date = assignment.date.strftime("%A, %B %d, %Y")
    subject_prefix = "[Manage2Soar]"

    # 1. Ad-hoc day created (no crew yet)
    if not assignment.tow_pilot and not assignment.duty_officer:
        send_mail(
            subject=f"{subject_prefix} Ad-Hoc Operations Proposed for {ops_date}",
            message=f"An ad-hoc ops day has been proposed for {ops_date}.\n\nTow pilots and duty officers needed!\n\nCalendar: {settings.SITE_URL}/duty_roster/calendar/",
            from_email="noreply@default.manage2soar.com",
            recipient_list=["instructors@default.manage2soar.com",
                            "towpilots@default.manage2soar.com"],
        )
        return

    # 2. Ad-hoc ops day now confirmed
    if assignment.tow_pilot and assignment.duty_officer and not assignment.is_scheduled:
        if not assignment.is_confirmed:
            print("📣 Minimum crew present — confirming ops")
            assignment.is_confirmed = True
            assignment.save()

            send_mail(
                subject=f"{subject_prefix} Ad-Hoc Ops Confirmed for {ops_date}",
                message=f"We now have a tow pilot and duty officer for {ops_date} — operations are a go!\n\nCalendar: {settings.SITE_URL}/duty_roster/calendar/",
                from_email="noreply@default.manage2soar.com",
                recipient_list=["members@default.manage2soar.com"],
            )
