"""
ICS calendar file generation utilities for duty roster assignments.

This module provides functions to generate ICS (iCalendar) files for duty
assignments, which can be attached to notification emails to allow members
to easily add their duty assignments to their personal calendars.
"""

from datetime import datetime, timedelta

from django.conf import settings
from icalendar import Calendar, Event, vText

from siteconfig.models import SiteConfiguration


def generate_duty_ics(
    duty_date,
    role_title,
    member_name,
    location=None,
    notes=None,
    uid_suffix=None,
):
    """
    Generate an ICS file for a duty assignment.

    Args:
        duty_date: date object for the duty assignment
        role_title: Title of the duty role (e.g., "Duty Officer", "Tow Pilot")
        member_name: Name of the member assigned to this duty
        location: Optional location string (defaults to club name from config)
        notes: Optional additional notes for the event description
        uid_suffix: Optional suffix for unique event ID

    Returns:
        bytes: ICS file content as bytes, ready to attach to email
    """
    config = SiteConfiguration.objects.first()
    club_name = config.club_name if config else "Soaring Club"
    domain_name = config.domain_name if config else "manage2soar.com"

    # Create calendar
    cal = Calendar()
    cal.add("prodid", f"-//Manage2Soar//{club_name}//EN")
    cal.add("version", "2.0")
    cal.add("method", "PUBLISH")

    # Create event
    event = Event()

    # Summary: role title and club name
    event.add("summary", f"{role_title} - {club_name}")

    # Description with details
    description_parts = [
        f"You have been assigned as {role_title} for {club_name}.",
        f"Assigned to: {member_name}",
    ]
    if notes:
        description_parts.append(f"Notes: {notes}")

    # Add site URL to description if available
    site_url = getattr(settings, "SITE_URL", "")
    if site_url:
        description_parts.append(
            f"\nView duty roster: {site_url}/duty_roster/calendar/"
        )

    event.add("description", "\n".join(description_parts))

    # All-day event for duty date
    event.add("dtstart", duty_date)
    event.add("dtend", duty_date + timedelta(days=1))

    # Location
    if location:
        event.add("location", location)
    elif config and hasattr(config, "club_address") and config.club_address:
        event.add("location", config.club_address)
    else:
        event.add("location", club_name)

    # Unique ID for the event
    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    role_slug = role_title.lower().replace(" ", "-")
    uid_base = f"{duty_date.isoformat()}-{role_slug}"
    if uid_suffix:
        uid_base += f"-{uid_suffix}"
    event.add("uid", f"{uid_base}-{timestamp}@{domain_name}")

    # Add timestamp
    event.add("dtstamp", datetime.now())

    # Add organizer (club email)
    default_from = getattr(settings, "DEFAULT_FROM_EMAIL", "")
    if default_from:
        event.add("organizer", f"MAILTO:{default_from}")

    # Status
    event.add("status", "CONFIRMED")

    # Add event to calendar
    cal.add_component(event)

    return cal.to_ical()


def generate_swap_ics(
    swap_request,
    for_member,
    is_original_requester=True,
):
    """
    Generate ICS file for a duty swap confirmation.

    Args:
        swap_request: DutySwapRequest object with accepted offer
        for_member: Member object this ICS is being generated for
        is_original_requester: True if generating for original requester,
                               False if for the member who accepted the swap

    Returns:
        bytes: ICS file content as bytes
    """
    config = SiteConfiguration.objects.first()
    club_name = config.club_name if config else "Soaring Club"
    domain_name = config.domain_name if config else "manage2soar.com"

    # Get role title
    role_title = swap_request.get_role_title()
    offer = swap_request.accepted_offer

    cal = Calendar()
    cal.add("prodid", f"-//Manage2Soar//{club_name}//EN")
    cal.add("version", "2.0")
    cal.add("method", "PUBLISH")

    events_to_add = []

    if is_original_requester:
        # Original requester no longer has duty on original_date
        # If it was a swap, they now have duty on the proposed_swap_date
        if offer.offer_type == "swap" and offer.proposed_swap_date:
            # Add new duty assignment for the swap date
            event = Event()
            event.add("summary", f"{role_title} - {club_name}")
            event.add(
                "description",
                f"Swapped duty: You now have {role_title} duty.\n"
                f"(Swapped with {offer.offered_by.full_display_name})",
            )
            event.add("dtstart", offer.proposed_swap_date)
            event.add("dtend", offer.proposed_swap_date + timedelta(days=1))
            timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
            event.add(
                "uid",
                f"{offer.proposed_swap_date.isoformat()}-{role_title.lower().replace(' ', '-')}"
                f"-swap-{swap_request.pk}-{timestamp}@{domain_name}",
            )
            event.add("dtstamp", datetime.now())
            event.add("status", "CONFIRMED")
            events_to_add.append(event)
    else:
        # Person who offered the swap/cover now has duty on original_date
        event = Event()
        event.add("summary", f"{role_title} - {club_name}")

        if offer.offer_type == "swap":
            event.add(
                "description",
                f"Swapped duty: You now have {role_title} duty.\n"
                f"(Swapped with {swap_request.requester.full_display_name})",
            )
        else:
            event.add(
                "description",
                f"Coverage duty: You are covering as {role_title}.\n"
                f"(Covering for {swap_request.requester.full_display_name})",
            )

        event.add("dtstart", swap_request.original_date)
        event.add("dtend", swap_request.original_date + timedelta(days=1))
        timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
        event.add(
            "uid",
            f"{swap_request.original_date.isoformat()}-{role_title.lower().replace(' ', '-')}"
            f"-cover-{swap_request.pk}-{timestamp}@{domain_name}",
        )
        event.add("dtstamp", datetime.now())
        event.add("status", "CONFIRMED")
        events_to_add.append(event)

    # Add location to all events
    location = None
    if config and hasattr(config, "club_address") and config.club_address:
        location = config.club_address
    else:
        location = club_name

    for event in events_to_add:
        event.add("location", location)
        cal.add_component(event)

    return cal.to_ical()


def generate_preop_ics(assignment, for_member, role_title):
    """
    Generate ICS file for a pre-op duty assignment notification.

    Args:
        assignment: DutyAssignment object
        for_member: Member object receiving the notification
        role_title: The role this member is assigned to

    Returns:
        bytes: ICS file content as bytes
    """
    notes = f"Assignment confirmed via pre-op notification."
    return generate_duty_ics(
        duty_date=assignment.date,
        role_title=role_title,
        member_name=for_member.full_display_name,
        notes=notes,
        uid_suffix=f"preop-{assignment.pk}",
    )
