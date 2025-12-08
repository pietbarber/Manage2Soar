from django.conf import settings
from django.template.loader import render_to_string

from siteconfig.models import SiteConfiguration
from utils.email import send_mail
from utils.email_helpers import get_absolute_club_logo_url


def notify_ops_status(assignment):
    print(
        f"🧠 State: tow_pilot={assignment.tow_pilot}, duty_officer={assignment.duty_officer}, confirmed={assignment.is_confirmed}"
    )

    if not assignment or assignment.is_scheduled:
        return  # Ignore scheduled days

    ops_date = assignment.date.strftime("%A, %B %d, %Y")
    subject_prefix = "[Manage2Soar]"

    from siteconfig.utils import get_role_title

    # 1. Ad-hoc day created (no crew yet)
    if not assignment.tow_pilot and not assignment.duty_officer:
        # Get configuration
        config = SiteConfiguration.objects.first()
        club_name = config.club_name if config else "Manage2Soar"
        site_url = (
            f"https://{config.domain_name}"
            if config and config.domain_name
            else settings.SITE_URL
        )
        roster_url = f"{site_url}/duty_roster/"

        # Build from_email
        from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None)
        if not from_email and config and config.domain_name:
            from_email = f"noreply@{config.domain_name}"
        if not from_email:
            from_email = "noreply@default.manage2soar.com"

        # Build recipient_list
        instructors_list = getattr(settings, "INSTRUCTORS_MAILING_LIST", None)
        if not instructors_list and config and config.domain_name:
            instructors_list = f"instructors@{config.domain_name}"
        if not instructors_list:
            instructors_list = "instructors@default.manage2soar.com"

        towpilots_list = getattr(settings, "TOWPILOTS_MAILING_LIST", None)
        if not towpilots_list and config and config.domain_name:
            towpilots_list = f"towpilots@{config.domain_name}"
        if not towpilots_list:
            towpilots_list = "towpilots@default.manage2soar.com"

        recipient_list = [instructors_list, towpilots_list]

        # Render email
        from siteconfig.utils import get_role_title

        tow_title = get_role_title("towpilot") or "Tow Pilot"
        do_title = get_role_title("duty_officer") or "Duty Officer"

        context = {
            "ops_date": assignment.date,
            "tow_title": tow_title,
            "do_title": do_title,
            "club_name": club_name,
            "club_logo_url": get_absolute_club_logo_url(config),
            "roster_url": roster_url,
        }
        html_message = render_to_string(
            "duty_roster/emails/ad_hoc_proposed.html", context
        )
        text_message = render_to_string(
            "duty_roster/emails/ad_hoc_proposed.txt", context
        )

        send_mail(
            subject=f"[{club_name}] Ad-Hoc Operations Proposed for {ops_date}",
            message=text_message,
            from_email=from_email,
            recipient_list=recipient_list,
            html_message=html_message,
        )
        return

    # 2. Ad-hoc ops day now confirmed
    if assignment.tow_pilot and assignment.duty_officer and not assignment.is_scheduled:
        if not assignment.is_confirmed:
            print("📣 Minimum crew present — confirming ops")
            assignment.is_confirmed = True
            assignment.save()

            # Get configuration
            config = SiteConfiguration.objects.first()
            club_name = config.club_name if config else "Manage2Soar"
            site_url = (
                f"https://{config.domain_name}"
                if config and config.domain_name
                else settings.SITE_URL
            )
            roster_url = f"{site_url}/duty_roster/"

            # Build from_email
            from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None)
            if not from_email and config and config.domain_name:
                from_email = f"noreply@{config.domain_name}"
            if not from_email:
                from_email = "noreply@default.manage2soar.com"

            # Build recipient_list
            members_list = getattr(settings, "MEMBERS_MAILING_LIST", None)
            if not members_list and config and config.domain_name:
                members_list = f"members@{config.domain_name}"
            if not members_list:
                members_list = "members@default.manage2soar.com"
            recipient_list = [members_list]

            # Render email
            from siteconfig.utils import get_role_title

            tow_title = get_role_title("towpilot") or "Tow Pilot"
            do_title = get_role_title("duty_officer") or "Duty Officer"

            context = {
                "ops_date": assignment.date,
                "tow_title": tow_title,
                "do_title": do_title,
                "club_name": club_name,
                "club_logo_url": get_absolute_club_logo_url(config),
                "roster_url": roster_url,
            }
            html_message = render_to_string(
                "duty_roster/emails/ad_hoc_confirmed.html", context
            )
            text_message = render_to_string(
                "duty_roster/emails/ad_hoc_confirmed.txt", context
            )

            send_mail(
                subject=f"[{club_name}] Ad-Hoc Ops Confirmed for {ops_date}",
                message=text_message,
                from_email=from_email,
                recipient_list=recipient_list,
                html_message=html_message,
            )
