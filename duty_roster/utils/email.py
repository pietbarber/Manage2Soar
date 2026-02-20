from collections import defaultdict
from datetime import date

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

from duty_roster.utils.ics import generate_roster_ics
from siteconfig.models import SiteConfiguration
from siteconfig.utils import get_role_title
from utils.email import send_mail
from utils.email_helpers import get_absolute_club_logo_url
from utils.url_helpers import build_absolute_url, get_canonical_url


def get_email_config():
    """Get common email configuration settings for all duty roster emails.

    Returns:
        dict: Configuration containing config, site_url, roster_url, from_email, and club_name
    """
    config = SiteConfiguration.objects.first()
    site_url = get_canonical_url()
    roster_url = build_absolute_url("/duty_roster/calendar/", canonical=site_url)

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

    # 1. Ad-hoc day created (no crew yet)
    if not assignment.tow_pilot and not assignment.duty_officer:
        # Get configuration
        email_config = get_email_config()
        # Notify all members so duty officers, tow pilots, and instructors all
        # see the call-to-action exactly once.  Previous approach of targeting
        # INSTRUCTORS + TOWPILOTS lists caused duplicate emails for multi-role
        # members and completely missed duty officers (issue #654).
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


def send_roster_published_notifications(year, month, assignments):
    """
    Send ICS calendar invites to all members who have duty assignments
    for a newly published roster month.

    Args:
        year: The year of the roster
        month: The month of the roster
        assignments: List of DutyAssignment objects for the month

    Returns:
        dict: Summary with 'sent_count', 'member_count', and 'errors'
    """
    # Get configuration
    email_config = get_email_config()
    config = email_config["config"]

    # Group assignments by member
    member_assignments = defaultdict(list)

    # Role field mapping
    role_fields = [
        ("duty_officer", "duty_officer"),
        ("assistant_duty_officer", "assistant_duty_officer"),
        ("instructor", "instructor"),
        ("tow_pilot", "towpilot"),
        ("surge_instructor", "surge_instructor"),
        ("surge_tow_pilot", "surge_towpilot"),
    ]

    # Cache role titles to avoid repeated database lookups in get_role_title
    role_titles = {role_key: get_role_title(role_key) for _, role_key in role_fields}

    for assignment in assignments:
        for field_name, role_key in role_fields:
            member = getattr(assignment, field_name, None)
            if member and member.email:
                role_title = role_titles.get(role_key)
                # Skip if role title is None or empty
                if not role_title:
                    continue
                member_assignments[member].append(
                    {
                        "date": assignment.date,
                        "role": role_title,
                        "assignment": assignment,
                    }
                )

    if not member_assignments:
        return {"sent_count": 0, "member_count": 0, "errors": []}

    # Format month name
    month_name = date(year, month, 1).strftime("%B %Y")

    # Build context for templates
    context = {
        "month_name": month_name,
        "year": year,
        "month": month,
        "club_name": email_config["club_name"],
        "club_nickname": config.club_nickname if config else None,
        "club_logo_url": get_absolute_club_logo_url(config),
        "site_url": email_config["site_url"],
        "duty_roster_url": email_config["roster_url"],
    }

    sent_count = 0
    errors = []

    # TODO: For large rosters (50+ members), consider using Django's send_mass_mail
    # or a background task queue (Celery) to avoid blocking the request.
    # The current implementation handles partial failures gracefully with the errors list.
    for member, duty_list in member_assignments.items():
        # Sort duties by date
        duty_list.sort(key=lambda x: x["date"])

        # Build member-specific context
        member_context = context.copy()
        member_context["member"] = member
        member_context["duties"] = duty_list
        member_context["duty_count"] = len(duty_list)

        # Render email templates
        html_message = render_to_string(
            "duty_roster/emails/roster_published.html", member_context
        )
        text_message = render_to_string(
            "duty_roster/emails/roster_published.txt", member_context
        )

        # Create email
        subject = (
            f"[{email_config['club_name']}] Your Duty Assignments for {month_name}"
        )

        email = EmailMultiAlternatives(
            subject=subject,
            body=text_message,
            from_email=email_config["from_email"],
            to=[member.email],
        )
        email.attach_alternative(html_message, "text/html")

        # Attach ICS files for each duty
        for duty in duty_list:
            ics_content = generate_roster_ics(
                duty_date=duty["date"],
                role_title=duty["role"],
                member_name=member.full_display_name,
            )
            role_slug = duty["role"].lower().replace(" ", "-")
            ics_filename = f"duty-{duty['date'].isoformat()}-{role_slug}.ics"
            email.attach(ics_filename, ics_content, "text/calendar")

        try:
            email.send(fail_silently=False)
            sent_count += 1
        except Exception as e:
            errors.append(f"Failed to send to {member.email}: {str(e)}")

    return {
        "sent_count": sent_count,
        "member_count": len(member_assignments),
        "errors": errors,
    }
