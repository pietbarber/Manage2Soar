"""
ICS calendar file generation utilities for duty roster assignments.

This module provides functions to generate ICS (iCalendar) files for duty
assignments, which can be attached to notification emails to allow members
to easily add their duty assignments to their personal calendars.
"""

from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from icalendar import Calendar, Event

from siteconfig.models import SiteConfiguration
from utils.url_helpers import build_absolute_url


def _build_club_location(config, fallback):
    """Return a formatted location string from SiteConfiguration address fields.

    SiteConfiguration does not have a single ``club_address`` field; the address
    is split across ``club_address_line1``, ``club_address_line2``, ``club_city``,
    ``club_state``, ``club_zip_code``, and ``club_country``.  Falls back to
    *fallback* (typically ``club_name``) when no address fields are populated.
    """
    if not config:
        return fallback
    parts = []
    line1 = getattr(config, "club_address_line1", None)
    line2 = getattr(config, "club_address_line2", None)
    city = getattr(config, "club_city", None)
    state = getattr(config, "club_state", None)
    zip_code = getattr(config, "club_zip_code", None)
    country = getattr(config, "club_country", None)
    if line1:
        parts.append(line1)
    if line2:
        parts.append(line2)
    city_state_zip = " ".join(p for p in [city, state, zip_code] if p)
    if city_state_zip:
        parts.append(city_state_zip)
    # Only include country when other address components are present.
    # SiteConfiguration.club_country defaults to "USA", so appending it
    # unconditionally would produce a location of just "USA" for a config with
    # no other address fields set — which is less useful than falling back to
    # club_name.
    if country and parts:
        parts.append(country)
    return ", ".join(parts) if parts else fallback


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

    # Add duty roster link
    description_parts.append(
        f"\nView duty roster: {build_absolute_url('/duty_roster/calendar/')}"
    )

    event.add("description", "\n".join(description_parts))

    # All-day event for duty date
    event.add("dtstart", duty_date)
    event.add("dtend", duty_date + timedelta(days=1))

    # Location
    if location:
        event.add("location", location)
    else:
        event.add("location", _build_club_location(config, club_name))

    # Unique ID for the event
    now = timezone.now()
    timestamp = now.strftime("%Y%m%dT%H%M%S")
    role_slug = role_title.lower().replace(" ", "-")
    uid_base = f"{duty_date.isoformat()}-{role_slug}"
    if uid_suffix:
        uid_base += f"-{uid_suffix}"
    event.add("uid", f"{uid_base}-{timestamp}@{domain_name}")

    # Add timestamp (must be UTC per RFC 5545)
    event.add("dtstamp", now)

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
            now = timezone.now()
            timestamp = now.strftime("%Y%m%dT%H%M%S")
            event.add(
                "uid",
                f"{offer.proposed_swap_date.isoformat()}-{role_title.lower().replace(' ', '-')}"
                f"-swap-{swap_request.pk}-{timestamp}@{domain_name}",
            )
            event.add("dtstamp", now)
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
        now = timezone.now()
        timestamp = now.strftime("%Y%m%dT%H%M%S")
        event.add(
            "uid",
            f"{swap_request.original_date.isoformat()}-{role_title.lower().replace(' ', '-')}"
            f"-cover-{swap_request.pk}-{timestamp}@{domain_name}",
        )
        event.add("dtstamp", now)
        event.add("status", "CONFIRMED")
        events_to_add.append(event)

    # Add location to all events
    location = _build_club_location(config, club_name)

    # Return None if no events (e.g., requester in cover scenario has no new duty)
    if not events_to_add:
        return None

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
    notes = "Assignment confirmed via pre-op notification."
    return generate_duty_ics(
        duty_date=assignment.date,
        role_title=role_title,
        member_name=for_member.full_display_name,
        notes=notes,
        uid_suffix=f"preop-{assignment.pk}",
    )


def generate_ops_day_ics(duty_date):
    """
    Generate a generic ICS calendar event for an operations day.

    Intended for non-crew participants (ops intent members, students) who will
    be flying on the day but do not have a specific crew duty assignment.
    Each recipient gets their own copy, but the content is not personalized to
    any individual crew role.

    Args:
        duty_date: date object for the operations day

    Returns:
        bytes: ICS file content as bytes
    """
    config = SiteConfiguration.objects.first()
    club_name = config.club_name if config else "Soaring Club"
    # Use a fallback when domain_name is missing or an empty string (not only None)
    domain_name = (config.domain_name if config else None) or "manage2soar.com"

    cal = Calendar()
    cal.add("prodid", f"-//Manage2Soar//{club_name}//EN")
    cal.add("version", "2.0")
    cal.add("method", "PUBLISH")

    event = Event()
    event.add("summary", f"Flying Day - {club_name}")

    description_parts = [
        f"Flying operations at {club_name}.",
        f"\nView duty roster: {build_absolute_url('/duty_roster/calendar/')}",
    ]
    event.add("description", "\n".join(description_parts))

    event.add("dtstart", duty_date)
    event.add("dtend", duty_date + timedelta(days=1))

    event.add("location", _build_club_location(config, club_name))

    now_dt = timezone.now()
    # Use a stable UID (no timestamp) so that re-sending the same flying-day
    # ICS updates the existing calendar entry rather than creating duplicates.
    event.add("uid", f"{duty_date.isoformat()}-flying-day@{domain_name}")
    event.add("dtstamp", now_dt)
    event.add("status", "CONFIRMED")

    default_from = getattr(settings, "DEFAULT_FROM_EMAIL", "")
    if default_from:
        event.add("organizer", f"MAILTO:{default_from}")

    cal.add_component(event)
    return cal.to_ical()


def generate_roster_ics(duty_date, role_title, member_name):
    """
    Generate ICS file for a newly established roster duty assignment.

    Args:
        duty_date: date object for the duty assignment
        role_title: The role assigned (e.g., "Duty Officer")
        member_name: Name of the assigned member

    Returns:
        bytes: ICS file content as bytes
    """
    notes = "Duty assignment from newly published roster."
    # Build a stable UID suffix based only on date, role, and member.
    # This will be used as the final UID so that re-publishing the same
    # roster updates existing calendar entries instead of creating
    # duplicates.
    role_slug = role_title.lower().replace(" ", "-")
    member_slug = member_name.lower().replace(" ", "-")
    uid_suffix = f"roster-{duty_date.isoformat()}-{role_slug}-{member_slug}"

    # First, generate a baseline ICS using the shared helper. This may
    # include a timestamp in the UID, which we do *not* want for roster
    # publications.
    ics_bytes = generate_duty_ics(
        duty_date=duty_date,
        role_title=role_title,
        member_name=member_name,
        notes=notes,
        uid_suffix=uid_suffix,
    )

    # Parse the calendar and overwrite the UID of all VEVENT components
    # with our stable, timestamp-free value derived from the assignment.
    calendar = Calendar.from_ical(ics_bytes.decode("utf-8"))
    for component in calendar.walk():
        if getattr(component, "name", None) == "VEVENT":
            component["uid"] = uid_suffix

    return calendar.to_ical()
