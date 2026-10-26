"""
Shared eligibility validation for flight participant assignments.

Used by the offline sync API (``logsheet/api.py``) to enforce the same
pilot, instructor, tow-pilot, and passenger eligibility rules as the
FlightForm.  The form enforces the rules through queryset restriction;
the API has no form, so it must validate explicitly.

Rules enforced (mirrors FlightForm.set_member_groups):
  * Deceased members are never eligible (hard block, no exception).
  * The unchanged non-deceased assignment is always allowed (exception).
  * Pilot:      status must have ``can_be_pilot=True``.
  * Passenger:  status must have ``can_be_passenger=True``.
  * Instructor: member must have ``instructor=True`` OR status == "Instructor".
  * Tow pilot:  member must have ``towpilot=True``.
  * Instructor / tow pilot: status must be active, visiting, "Inactive",
    or (for instructor) "Instructor".
  * When visiting pilots are disabled, the visiting status is excluded from
    every participant field (applied *before* the unchanged-assignment
    exception, so the exception re-includes it only for the current value).
"""

from members.models import Member
from members.utils.membership import get_active_membership_statuses
from siteconfig.models import MembershipStatus, SiteConfiguration


def get_eligibility_context():
    """
    Return eligibility parameters derived from site configuration and
    membership status flags.

    Returns:
        dict with keys:
          - active_statuses: list[str]
          - pilot_eligible_statuses: set[str]
          - passenger_eligible_statuses: set[str]
          - visiting_status: str
          - visiting_enabled: bool
    """
    config = SiteConfiguration.objects.first()
    active_statuses = list(get_active_membership_statuses())
    pilot_eligible_statuses = set(
        MembershipStatus.objects.filter(can_be_pilot=True).values_list(
            "name", flat=True
        )
    )
    passenger_eligible_statuses = set(
        MembershipStatus.objects.filter(can_be_passenger=True).values_list(
            "name", flat=True
        )
    )
    if config is None:
        visiting_status = "Affiliate Member"
        visiting_enabled = False
    else:
        visiting_status = config.visiting_pilot_status or "Affiliate Member"
        visiting_enabled = bool(config.visiting_pilot_enabled and visiting_status)
    return {
        "active_statuses": active_statuses,
        "pilot_eligible_statuses": pilot_eligible_statuses,
        "passenger_eligible_statuses": passenger_eligible_statuses,
        "visiting_status": visiting_status,
        "visiting_enabled": visiting_enabled,
    }


def validate_member_for_role(
    member,
    field_name,
    context,
    *,
    existing_assignment_id=None,
):
    """
    Validate that a member is eligible for the given flight role.

    Args:
        member: Member instance (or None, in which case returns None).
        field_name: "pilot" | "instructor" | "tow_pilot" | "passenger".
        context: dict from ``get_eligibility_context()``.
        existing_assignment_id: If set and equals ``member.pk``, the
            unchanged non-deceased assignment exception applies (bypasses
            all eligibility checks except the Deceased hard block).

    Returns:
        None if eligible, or an error message string if not.
    """
    if member is None:
        return None

    # Hard block: deceased members are never eligible, no exception.
    if member.membership_status == "Deceased":
        return f"Deceased members cannot be assigned as {field_name}."

    # Unchanged-assignment exception: the existing (non-deceased) value is
    # always allowed, bypassing field-specific, status, and visiting checks.
    if existing_assignment_id is not None and member.pk == existing_assignment_id:
        return None

    # Field-specific role requirement.
    if field_name == "instructor":
        if not (member.instructor or member.membership_status == "Instructor"):
            return f"{member} is not qualified as an instructor."
    elif field_name == "tow_pilot":
        if not member.towpilot:
            return f"{member} is not qualified as a tow pilot."

    # Status-based eligibility.
    if field_name == "pilot":
        if member.membership_status not in context["pilot_eligible_statuses"]:
            return f"{member} is not eligible to be a pilot."
    elif field_name == "passenger":
        if member.membership_status not in context["passenger_eligible_statuses"]:
            return f"{member} is not eligible to be a passenger."
    else:
        allowed = set(context["active_statuses"]) | {
            context["visiting_status"],
            "Inactive",
        }
        if field_name == "instructor":
            allowed |= {"Instructor"}
        if member.membership_status not in allowed:
            return f"{member} is not eligible for the {field_name} role."

    # Visiting filter (applied to every participant field when disabled).
    if (
        not context["visiting_enabled"]
        and context["visiting_status"]
        and member.membership_status == context["visiting_status"]
    ):
        return (
            f"Visiting pilots are disabled; {member} cannot be "
            f"assigned as {field_name}."
        )

    return None


def validate_flight_assignments(
    assignments: dict,
    *,
    existing_assignments: dict | None = None,
) -> dict:
    """
    Validate a batch of role assignments.

    Args:
        assignments: dict mapping field_name -> Member (or None).
            e.g. {"pilot": m1, "passenger": m2, ...}
        existing_assignments: Optional dict mapping field_name -> existing
            Member PK. Used for the unchanged-assignment exception.

    Returns:
        dict mapping field_name -> error message for invalid assignments.
        Empty dict means all assignments are valid.
    """
    context = get_eligibility_context()
    errors = {}
    existing_assignments = existing_assignments or {}
    for field_name, member in assignments.items():
        if member is None:
            continue
        existing_id = existing_assignments.get(field_name)
        error = validate_member_for_role(
            member, field_name, context, existing_assignment_id=existing_id
        )
        if error:
            errors[field_name] = error
    return errors


def validate_participant_combination(
    pilot=None, instructor=None, tow_pilot=None, passenger=None
) -> dict:
    """
    Validate that no member holds two mutually-exclusive roles on the same
    flight.

    Mirrors ``FlightForm.clean()`` role-conflict checks so the offline sync
    API (which has no form) enforces the same rules as the web form:
      * pilot == instructor
      * pilot == passenger
      * instructor == passenger
      * pilot == tow_pilot

    Args:
        pilot, instructor, tow_pilot, passenger: Member instances or None.

    Returns:
        dict mapping ``"<role_a>_vs_<role_b>"`` -> error message for each
        conflict found.  Empty dict means the combination is valid.
    """
    errors = {}

    if pilot and instructor and pilot.pk == instructor.pk:
        errors["pilot_vs_instructor"] = (
            f"{pilot} cannot be both pilot and instructor on the same flight."
        )
    if pilot and passenger and pilot.pk == passenger.pk:
        errors["pilot_vs_passenger"] = (
            f"{pilot} cannot be both pilot and passenger on the same flight."
        )
    if instructor and passenger and instructor.pk == passenger.pk:
        errors["instructor_vs_passenger"] = (
            f"{instructor} cannot be both instructor and passenger on the same flight."
        )
    if pilot and tow_pilot and pilot.pk == tow_pilot.pk:
        errors["pilot_vs_tow_pilot"] = (
            f"{pilot} cannot be both pilot and tow pilot on the same flight."
        )

    return errors
