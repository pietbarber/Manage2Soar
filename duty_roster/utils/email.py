from django.conf import settings
from django.template.loader import render_to_string

from siteconfig.models import SiteConfiguration
from siteconfig.utils import get_role_title
from utils.email import send_mail
from utils.email_helpers import get_absolute_club_logo_url


def get_email_config():
    """Get common email configuration settings for all duty roster emails.

    Returns:
        dict: Configuration containing config, site_url, roster_url, from_email, and club_name
    """
    config = SiteConfiguration.objects.first()
    site_url = getattr(settings, "SITE_URL", "").rstrip("/")
    roster_url = (
        f"{site_url}/duty_roster/calendar/" if site_url else "/duty_roster/calendar/"
    )

    # Build from_email
    default_from = getattr(settings, "DEFAULT_FROM_EMAIL", "") or ""
    if "@" in default_from:
        domain = default_from.split("@")[-1]
        from_email = f"noreply@{domain}"
    elif config and config.domain_name:
        from_email = f"noreply@{config.domain_name}"
    else:
        from_email = "noreply@manage2soar.com"

    return {
        "config": config,
        "site_url": site_url,
        "roster_url": roster_url,
        "from_email": from_email,
        "club_name": config.club_name if config else "Soaring Club",
    }


def get_mailing_list(setting_name, fallback_prefix, config=None):
    """Get mailing list from settings or construct from config domain.

    Args:
        setting_name: Name of the settings variable (e.g., 'INSTRUCTORS_MAILING_LIST')
        fallback_prefix: Email prefix to use (e.g., 'instructors')
        config: SiteConfiguration object (optional, will fetch if not provided)

    Returns:
        list: List containing the mailing list address
    """
    if config is None:
        config = SiteConfiguration.objects.first()

    mailing_list = getattr(settings, setting_name, "") or ""
    if "@" in mailing_list:
        return [mailing_list]
    elif config and config.domain_name:
        return [f"{fallback_prefix}@{config.domain_name}"]
    else:
        return [f"{fallback_prefix}@manage2soar.com"]


def notify_ops_status(assignment):
    print(
        f"🧠 State: tow_pilot={assignment.tow_pilot}, duty_officer={assignment.duty_officer}, confirmed={assignment.is_confirmed}"
    )

    if not assignment or assignment.is_scheduled:
        return  # Ignore scheduled days

    ops_date = assignment.date.strftime("%A, %B %d, %Y")
    subject_prefix = "[Manage2Soar]"

    # 1. Ad-hoc day created (no crew yet)
    if not assignment.tow_pilot and not assignment.duty_officer:
        # Get configuration
        email_config = get_email_config()
        recipient_list = get_mailing_list(
            "INSTRUCTORS_MAILING_LIST", "instructors", email_config["config"]
        ) + get_mailing_list(
            "TOWPILOTS_MAILING_LIST", "towpilots", email_config["config"]
        )

        tow_title = get_role_title("towpilot") or "Tow Pilot"
        do_title = get_role_title("duty_officer") or "Duty Officer"

        context = {
            "ops_date": ops_date,
            "tow_title": tow_title,
            "do_title": do_title,
            "club_name": email_config["club_name"],
            "club_logo_url": get_absolute_club_logo_url(email_config["config"]),
            "roster_url": email_config["roster_url"],
        }
        html_message = render_to_string(
            "duty_roster/emails/ad_hoc_proposed.html", context
        )
        text_message = render_to_string(
            "duty_roster/emails/ad_hoc_proposed.txt", context
        )

        send_mail(
            subject=f"[{email_config['club_name']}] Ad-Hoc Operations Proposed for {ops_date}",
            message=text_message,
            from_email=email_config["from_email"],
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
            email_config = get_email_config()
            recipient_list = get_mailing_list(
                "MEMBERS_MAILING_LIST", "members", email_config["config"]
            )

            tow_title = get_role_title("towpilot") or "Tow Pilot"
            do_title = get_role_title("duty_officer") or "Duty Officer"

            context = {
                "ops_date": ops_date,
                "tow_title": tow_title,
                "do_title": do_title,
                "club_name": email_config["club_name"],
                "club_logo_url": get_absolute_club_logo_url(email_config["config"]),
                "roster_url": email_config["roster_url"],
            }
            html_message = render_to_string(
                "duty_roster/emails/ad_hoc_confirmed.html", context
            )
            text_message = render_to_string(
                "duty_roster/emails/ad_hoc_confirmed.txt", context
            )

            send_mail(
                subject=f"[{email_config['club_name']}] Ad-Hoc Ops Confirmed for {ops_date}",
                message=text_message,
                from_email=email_config["from_email"],
                recipient_list=recipient_list,
                html_message=html_message,
            )
