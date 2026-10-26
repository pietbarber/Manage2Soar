import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from duty_roster.models import GliderReservation
from logsheet.forms import FlightForm
from logsheet.models import Flight
from siteconfig.models import MemberNameOrdering, MembershipStatus, SiteConfiguration


def _choice_groups(field):
    return {
        label: dict(options)
        for label, options in field.choices
        if isinstance(label, str) and isinstance(options, (list, tuple))
    }


def _group_member_ids(field, group_name):
    for label, options in field.choices:
        if label == group_name:
            return [member_id for member_id, _display in options]
    return []


@pytest.mark.django_db
def test_pilot_dropdown_defaults_to_last_name_and_honors_name_order_preference(
    logsheet,
):
    User = get_user_model()
    MembershipStatus.objects.get_or_create(
        name="Full Member",
        defaults={
            "is_active": True,
            "can_be_pilot": True,
            "can_be_passenger": True,
            "sort_order": 1,
        },
    )
    config = SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="test.example.com",
        club_abbreviation="TC",
    )
    ada = User.objects.create_user(
        username="ada-zulu",
        first_name="Ada",
        last_name="Zulu",
        membership_status="Full Member",
    )
    zoe = User.objects.create_user(
        username="zoe-alpha",
        first_name="Zoe",
        last_name="Alpha",
        membership_status="Full Member",
    )
    ben = User.objects.create_user(
        username="ben-alpha",
        first_name="Ben",
        last_name="Alpha",
        membership_status="Full Member",
    )

    form = FlightForm(logsheet=logsheet)
    assert config.member_name_ordering == MemberNameOrdering.LAST_NAME
    expected_member_ids = {ada.pk, zoe.pk, ben.pk}
    assert [
        member_id
        for member_id in _group_member_ids(form.fields["pilot"], "Active Members")
        if member_id in expected_member_ids
    ] == [ben.pk, zoe.pk, ada.pk]

    config.member_name_ordering = MemberNameOrdering.FIRST_NAME
    config.save(update_fields=["member_name_ordering"])
    form = FlightForm(logsheet=logsheet)
    assert [
        member_id
        for member_id in _group_member_ids(form.fields["pilot"], "Active Members")
        if member_id in expected_member_ids
    ] == [ada.pk, ben.pk, zoe.pk]


@pytest.mark.django_db
def test_today_roster_includes_reserved_and_flown_members_without_duplicates(
    active_member, logsheet, glider
):
    User = get_user_model()
    MembershipStatus.objects.get_or_create(
        name="Full Member",
        defaults={
            "is_active": True,
            "can_be_pilot": True,
            "can_be_passenger": True,
            "sort_order": 1,
        },
    )
    MembershipStatus.objects.get_or_create(
        name="Inactive", defaults={"is_active": False, "sort_order": 2}
    )
    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="test.example.com",
        club_abbreviation="TC",
    )
    reserved_member = User.objects.create_user(
        username="reserved-member",
        first_name="Reserved",
        last_name="Member",
        membership_status="Full Member",
    )
    flew_member = User.objects.create_user(
        username="flew-member",
        first_name="Flew",
        last_name="Member",
        membership_status="Full Member",
    )
    inactive_passenger = User.objects.create_user(
        username="inactive-passenger",
        first_name="Inactive",
        last_name="Passenger",
        membership_status="Inactive",
    )
    GliderReservation.objects.create(
        member=reserved_member,
        glider=glider,
        date=logsheet.log_date,
        status="confirmed",
    )
    Flight.objects.create(
        logsheet=logsheet,
        pilot=active_member,
        passenger=inactive_passenger,
        glider=glider,
    )
    Flight.objects.create(
        logsheet=logsheet,
        pilot=flew_member,
        glider=glider,
    )

    form = FlightForm(logsheet=logsheet)
    pilot_groups = _choice_groups(form.fields["pilot"])
    passenger_groups = _choice_groups(form.fields["passenger"])

    assert pilot_groups["Today’s Roster"] == {
        active_member.pk: str(active_member),
        reserved_member.pk: str(reserved_member),
        flew_member.pk: str(flew_member),
    }
    assert passenger_groups["Today’s Roster"] == {
        active_member.pk: str(active_member),
        reserved_member.pk: str(reserved_member),
        flew_member.pk: str(flew_member),
        inactive_passenger.pk: str(inactive_passenger),
    }
    assert all(
        member_id not in group
        for group_name, group in pilot_groups.items()
        if group_name != "Today’s Roster"
        for member_id in pilot_groups["Today’s Roster"]
    )


@pytest.mark.django_db
def test_today_roster_group_can_be_disabled(active_member, logsheet, glider):
    User = get_user_model()
    MembershipStatus.objects.get_or_create(
        name="Full Member",
        defaults={
            "is_active": True,
            "can_be_pilot": True,
            "can_be_passenger": True,
            "sort_order": 1,
        },
    )
    config = SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="test.example.com",
        club_abbreviation="TC",
        show_today_roster_group=False,
    )
    scheduled_member = User.objects.create_user(
        username="scheduled-member",
        first_name="Scheduled",
        last_name="Member",
        membership_status="Full Member",
    )
    GliderReservation.objects.create(
        member=scheduled_member,
        glider=glider,
        date=logsheet.log_date,
        status="confirmed",
    )

    form = FlightForm(logsheet=logsheet)
    pilot_groups = _choice_groups(form.fields["pilot"])
    assert "Today’s Roster" not in pilot_groups
    assert scheduled_member.pk in pilot_groups["Active Members"]


@pytest.mark.django_db
def test_inactive_members_remain_passengers_and_pilot_eligibility_uses_status(
    active_member, logsheet, glider
):
    User = get_user_model()
    MembershipStatus.objects.get_or_create(
        name="Full Member",
        defaults={
            "is_active": True,
            "can_be_pilot": True,
            "can_be_passenger": True,
            "sort_order": 1,
        },
    )
    MembershipStatus.objects.get_or_create(
        name="Inactive", defaults={"is_active": False, "sort_order": 2}
    )
    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="test.example.com",
        club_abbreviation="TC",
    )
    inactive_member = User.objects.create_user(
        username="inactive-choice",
        first_name="Inactive",
        last_name="Choice",
        membership_status="Inactive",
    )
    inactive_passenger = User.objects.create_user(
        username="inactive-pax-choice",
        first_name="Inactive",
        last_name="Pax",
        membership_status="Inactive",
    )
    GliderReservation.objects.create(
        member=inactive_member,
        glider=glider,
        date=logsheet.log_date,
        status="confirmed",
    )

    form = FlightForm(logsheet=logsheet)
    assert inactive_member.pk not in form.fields["pilot"].queryset.values_list(
        "pk", flat=True
    )
    passenger_groups = _choice_groups(form.fields["passenger"])
    assert inactive_member.pk in passenger_groups["Today’s Roster"]
    assert inactive_passenger.pk in passenger_groups["Not Active Members"]

    inactive_status = MembershipStatus.objects.get(name="Inactive")
    inactive_status.can_be_pilot = True
    inactive_status.save(update_fields=["can_be_pilot"])
    form = FlightForm(logsheet=logsheet)
    pilot_groups = _choice_groups(form.fields["pilot"])
    assert inactive_member.pk in pilot_groups["Today’s Roster"]


@pytest.mark.django_db
def test_custom_status_flight_eligibility_controls_pic_and_passenger_choices(
    active_member, logsheet
):
    User = get_user_model()
    MembershipStatus.objects.get_or_create(
        name="Full Member",
        defaults={
            "is_active": True,
            "can_be_pilot": True,
            "can_be_passenger": True,
            "sort_order": 1,
        },
    )
    MembershipStatus.objects.create(
        name="Former Member",
        is_active=False,
        can_be_pilot=False,
        can_be_passenger=True,
        sort_order=10,
    )
    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="test.example.com",
        club_abbreviation="TC",
    )
    former_member = User.objects.create_user(
        username="former-member",
        first_name="Former",
        last_name="Member",
        membership_status="Former Member",
    )

    form = FlightForm(logsheet=logsheet)
    assert former_member.pk not in form.fields["pilot"].queryset.values_list(
        "pk", flat=True
    )
    with pytest.raises(ValidationError):
        form.fields["pilot"].clean(former_member.pk)
    assert (
        former_member.pk
        in _choice_groups(form.fields["passenger"])["Not Active Members"]
    )


@pytest.mark.django_db
def test_ineligible_status_cannot_be_submitted_for_pilot_or_passenger(
    active_member, logsheet
):
    User = get_user_model()
    MembershipStatus.objects.get_or_create(
        name="Full Member",
        defaults={
            "is_active": True,
            "can_be_pilot": True,
            "can_be_passenger": True,
            "sort_order": 1,
        },
    )
    MembershipStatus.objects.create(
        name="Ground Member",
        is_active=False,
        can_be_pilot=False,
        can_be_passenger=False,
        sort_order=10,
    )
    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="test.example.com",
        club_abbreviation="TC",
    )
    ground_member = User.objects.create_user(
        username="ground-member",
        first_name="Ground",
        last_name="Member",
        membership_status="Ground Member",
    )

    form = FlightForm(logsheet=logsheet)
    for field_name in ("pilot", "passenger"):
        assert ground_member.pk not in form.fields[field_name].queryset.values_list(
            "pk", flat=True
        )
        with pytest.raises(ValidationError):
            form.fields[field_name].clean(ground_member.pk)


@pytest.mark.django_db
def test_deceased_status_never_appears_in_flight_member_choices(
    active_member, logsheet
):
    User = get_user_model()
    MembershipStatus.objects.get_or_create(
        name="Full Member",
        defaults={
            "is_active": True,
            "can_be_pilot": True,
            "can_be_passenger": True,
            "sort_order": 1,
        },
    )
    deceased_status, _ = MembershipStatus.objects.get_or_create(
        name="Deceased", defaults={"sort_order": 99}
    )
    deceased_status.is_active = True
    deceased_status.can_be_pilot = True
    deceased_status.can_be_passenger = True
    deceased_status.save(
        update_fields=["is_active", "can_be_pilot", "can_be_passenger"]
    )
    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="test.example.com",
        club_abbreviation="TC",
    )
    deceased_member = User.objects.create_user(
        username="deceased-member",
        first_name="Deceased",
        last_name="Member",
        membership_status="Deceased",
    )

    form = FlightForm(logsheet=logsheet)
    for field_name in ("pilot", "instructor", "tow_pilot", "passenger"):
        assert deceased_member.pk not in form.fields[field_name].queryset.values_list(
            "pk", flat=True
        )
        with pytest.raises(ValidationError):
            form.fields[field_name].clean(deceased_member.pk)


# ============================================================
# Regression tests for PR #1118 threads 1 & 4
# ============================================================


@pytest.mark.django_db
def test_visiting_disabled_blocks_eligible_visiting_participants_in_every_role(
    active_member, logsheet, glider
):
    """Thread 1: when visiting pilots are disabled, an eligible visiting
    instructor / tow pilot / passenger must NOT be selectable or submittable
    via any participant field, even when they appear in Today's Roster via
    a reservation or a confirmed instruction slot."""
    User = get_user_model()
    MembershipStatus.objects.get_or_create(
        name="Full Member",
        defaults={
            "is_active": True,
            "can_be_pilot": True,
            "can_be_passenger": True,
            "sort_order": 1,
        },
    )
    MembershipStatus.objects.get_or_create(
        name="Inactive", defaults={"is_active": False, "sort_order": 2}
    )
    visiting_status, _ = MembershipStatus.objects.get_or_create(
        name="Affiliate Member",
        defaults={
            "is_active": True,
            "can_be_pilot": True,
            "can_be_passenger": True,
            "sort_order": 5,
        },
    )
    visiting_status.can_be_pilot = True
    visiting_status.can_be_passenger = True
    visiting_status.save(update_fields=["can_be_pilot", "can_be_passenger"])
    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="test.example.com",
        club_abbreviation="TC",
        visiting_pilot_enabled=False,
        visiting_pilot_status="Affiliate Member",
        show_today_roster_group=True,
    )
    visiting_instructor = User.objects.create_user(
        username="visiting-instructor",
        first_name="Visiting",
        last_name="Instructor",
        membership_status="Affiliate Member",
        instructor=True,
    )
    visiting_towpilot = User.objects.create_user(
        username="visiting-towpilot",
        first_name="Visiting",
        last_name="TowPilot",
        membership_status="Affiliate Member",
        towpilot=True,
    )
    visiting_passenger = User.objects.create_user(
        username="visiting-passenger",
        first_name="Visiting",
        last_name="Passenger",
        membership_status="Affiliate Member",
    )
    # Put each of them on Today's Roster (via saved flights) so the
    # roster-based exception would otherwise admit them.
    Flight.objects.create(logsheet=logsheet, pilot=visiting_instructor, glider=glider)
    Flight.objects.create(logsheet=logsheet, pilot=visiting_towpilot, glider=glider)
    Flight.objects.create(
        logsheet=logsheet,
        pilot=active_member,
        passenger=visiting_passenger,
        glider=glider,
    )

    form = FlightForm(logsheet=logsheet)
    # With visiting disabled, a newly-selected visiting member must NOT
    # appear in the Today's Roster group (the display preference must not
    # change eligibility).  Each of the three visiting members is on the
    # roster via the saved flights above, so without the fix they would
    # leak into the roster group.
    for field_name in ("pilot", "instructor", "tow_pilot", "passenger"):
        roster_group = _choice_groups(form.fields[field_name]).get("Today’s Roster", {})
        assert (
            visiting_instructor.pk not in roster_group
        ), f"{field_name}: visiting instructor should not be in roster group"
        assert (
            visiting_towpilot.pk not in roster_group
        ), f"{field_name}: visiting tow pilot should not be in roster group"
        assert (
            visiting_passenger.pk not in roster_group
        ), f"{field_name}: visiting passenger should not be in roster group"

    # Newly-selected visiting members must not be submittable in their
    # natural roles either (the disabled-visiting filter applies to every
    # participant field, not just pilot).
    for field_name, member in (
        ("instructor", visiting_instructor),
        ("tow_pilot", visiting_towpilot),
        ("passenger", visiting_passenger),
    ):
        assert member.pk not in form.fields[field_name].queryset.values_list(
            "pk", flat=True
        ), f"{field_name}: visiting member should not be selectable"
        with pytest.raises(ValidationError):
            form.fields[field_name].clean(member.pk)


@pytest.mark.django_db
def test_existing_visiting_assignment_retained_when_visiting_and_roster_disabled(
    active_member, logsheet, glider
):
    """Thread 4: with visiting pilots AND Today's Roster grouping both
    disabled, an existing visiting assignment must remain in the visiting
    group so the unchanged value stays editable and the validation queryset
    does not reject it (which would block unrelated flight edits)."""
    User = get_user_model()
    MembershipStatus.objects.get_or_create(
        name="Full Member",
        defaults={
            "is_active": True,
            "can_be_pilot": True,
            "can_be_passenger": True,
            "sort_order": 1,
        },
    )
    visiting_status, _ = MembershipStatus.objects.get_or_create(
        name="Affiliate Member",
        defaults={
            "is_active": True,
            "can_be_pilot": True,
            "can_be_passenger": True,
            "sort_order": 5,
        },
    )
    visiting_status.can_be_pilot = True
    visiting_status.can_be_passenger = True
    visiting_status.save(update_fields=["can_be_pilot", "can_be_passenger"])
    config = SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="test.example.com",
        club_abbreviation="TC",
        visiting_pilot_enabled=False,
        visiting_pilot_status="Affiliate Member",
        show_today_roster_group=False,
    )
    visiting_pilot = User.objects.create_user(
        username="existing-visiting-pilot",
        first_name="Existing",
        last_name="Visiting",
        membership_status="Affiliate Member",
    )
    # An existing flight with the visiting member as pilot.
    existing_flight = Flight.objects.create(
        logsheet=logsheet,
        pilot=visiting_pilot,
        glider=glider,
    )

    form = FlightForm(instance=existing_flight, logsheet=logsheet)
    # The current visiting pilot must be present in the visiting group ...
    visiting_group = _choice_groups(form.fields["pilot"]).get("Visiting Pilots", {})
    assert visiting_pilot.pk in visiting_group
    # ... and in the validation queryset so the unchanged value is accepted.
    assert visiting_pilot.pk in form.fields["pilot"].queryset.values_list(
        "pk", flat=True
    )
    # An unrelated field can still be edited without rejecting the pilot.
    form.fields["pilot"].clean(visiting_pilot.pk)


@pytest.mark.django_db
def test_visiting_not_duplicated_when_roster_enabled_and_visiting_disabled(
    active_member, logsheet, glider
):
    """With visiting pilots disabled but Today's Roster grouping enabled, a
    saved visiting participant is already present in Today's Roster via the
    existing-assignment exception. The disabled-visiting fallback must NOT add
    the same member to the Visiting group again (which would produce duplicate
    options when editing the flight).  Querying ``remaining`` (which excludes
    rostered members) keeps the Deceased exclusion and avoids the duplicate."""
    User = get_user_model()
    MembershipStatus.objects.get_or_create(
        name="Full Member",
        defaults={
            "is_active": True,
            "can_be_pilot": True,
            "can_be_passenger": True,
            "sort_order": 1,
        },
    )
    visiting_status, _ = MembershipStatus.objects.get_or_create(
        name="Affiliate Member",
        defaults={
            "is_active": True,
            "can_be_pilot": True,
            "can_be_passenger": True,
            "sort_order": 5,
        },
    )
    visiting_status.can_be_pilot = True
    visiting_status.can_be_passenger = True
    visiting_status.save(update_fields=["can_be_pilot", "can_be_passenger"])
    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="test.example.com",
        club_abbreviation="TC",
        visiting_pilot_enabled=False,
        visiting_pilot_status="Affiliate Member",
        show_today_roster_group=True,
    )
    visiting_pilot = User.objects.create_user(
        username="dup-visiting-pilot",
        first_name="Dup",
        last_name="Visiting",
        membership_status="Affiliate Member",
    )
    existing_flight = Flight.objects.create(
        logsheet=logsheet,
        pilot=visiting_pilot,
        glider=glider,
    )

    form = FlightForm(instance=existing_flight, logsheet=logsheet)
    # Count how many times the visiting pilot appears across every optgroup.
    occurrences = sum(
        1
        for _label, options in form.fields["pilot"].choices
        if isinstance(options, (list, tuple))
        for member_id, _display in options
        if member_id == visiting_pilot.pk
    )
    # The member is on the roster (existing-assignment exception), so they must
    # appear exactly once — in Today's Roster — and NOT again in the Visiting
    # group (no duplicate).
    assert occurrences == 1, (
        f"visiting pilot should appear exactly once, found {occurrences}; "
        f"groups: {_choice_groups(form.fields['pilot'])}"
    )
    assert visiting_pilot.pk in _choice_groups(form.fields["pilot"])["Today’s Roster"]
    assert "Visiting Pilots" not in _choice_groups(form.fields["pilot"])
    # The unchanged value must still be accepted by the validation queryset.
    form.fields["pilot"].clean(visiting_pilot.pk)


# ============================================================
# Regression tests: role-flag removal + initial-value eligibility
# (PR #1118 follow-up, forms.py set_member_groups)
# ============================================================


@pytest.mark.django_db
def test_existing_assignment_retained_when_role_flag_removed(
    active_member, logsheet, glider
):
    """A saved instructor / tow pilot must stay editable after their role flag
    is removed.  ``validate_member_for_role`` allows the unchanged assignment
    regardless of qualification, so the form's validation queryset must keep
    the member selectable — even though the base role filter would otherwise
    drop them.  (Deceased members are still hard-excluded.)"""
    User = get_user_model()
    MembershipStatus.objects.get_or_create(
        name="Full Member",
        defaults={
            "is_active": True,
            "can_be_pilot": True,
            "can_be_passenger": True,
            "sort_order": 1,
        },
    )
    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="test.example.com",
        club_abbreviation="TC",
    )

    # --- Instructor: flag removed after the flight was saved ---------------
    removed_instructor = User.objects.create_user(
        username="removed-instructor",
        first_name="Removed",
        last_name="Instructor",
        membership_status="Full Member",
        instructor=True,
    )
    instructor_flight = Flight.objects.create(
        logsheet=logsheet,
        pilot=active_member,
        instructor=removed_instructor,
        glider=glider,
    )
    removed_instructor.instructor = False
    removed_instructor.save(update_fields=["instructor"])

    instructor_form = FlightForm(instance=instructor_flight, logsheet=logsheet)
    assert removed_instructor.pk in instructor_form.fields[
        "instructor"
    ].queryset.values_list(
        "pk", flat=True
    ), "saved instructor must stay selectable after the instructor flag is removed"
    instructor_form.fields["instructor"].clean(removed_instructor.pk)

    # --- Tow pilot: flag removed after the flight was saved -----------------
    removed_towpilot = User.objects.create_user(
        username="removed-towpilot",
        first_name="Removed",
        last_name="TowPilot",
        membership_status="Full Member",
        towpilot=True,
    )
    towpilot_flight = Flight.objects.create(
        logsheet=logsheet,
        pilot=active_member,
        tow_pilot=removed_towpilot,
        glider=glider,
    )
    removed_towpilot.towpilot = False
    removed_towpilot.save(update_fields=["towpilot"])

    towpilot_form = FlightForm(instance=towpilot_flight, logsheet=logsheet)
    assert removed_towpilot.pk in towpilot_form.fields[
        "tow_pilot"
    ].queryset.values_list(
        "pk", flat=True
    ), "saved tow pilot must stay selectable after the towpilot flag is removed"
    towpilot_form.fields["tow_pilot"].clean(removed_towpilot.pk)

    # A different, flag-less member must NOT become selectable through the
    # exception (the exception is scoped to the saved participant only).
    unqualified = User.objects.create_user(
        username="unqualified",
        first_name="Unqualified",
        last_name="Member",
        membership_status="Full Member",
        instructor=False,
        towpilot=False,
    )
    assert unqualified.pk not in instructor_form.fields[
        "instructor"
    ].queryset.values_list("pk", flat=True)
    assert unqualified.pk not in towpilot_form.fields["tow_pilot"].queryset.values_list(
        "pk", flat=True
    )


@pytest.mark.django_db
def test_initial_value_does_not_make_disallowed_member_selectable(
    active_member, logsheet, glider
):
    """``add_flight`` supplies the scheduled tow pilot through ``initial``.
    An initial value must only PRESELECT otherwise-eligible choices: it must
    not make a disallowed member selectable on GET and then have that same
    selection rejected on POST.  Here the disallowed member has the visiting
    status while visiting pilots are disabled."""
    User = get_user_model()
    MembershipStatus.objects.get_or_create(
        name="Full Member",
        defaults={
            "is_active": True,
            "can_be_pilot": True,
            "can_be_passenger": True,
            "sort_order": 1,
        },
    )
    visiting_status, _ = MembershipStatus.objects.get_or_create(
        name="Affiliate Member",
        defaults={
            "is_active": True,
            "can_be_pilot": True,
            "can_be_passenger": True,
            "sort_order": 5,
        },
    )
    visiting_status.can_be_pilot = True
    visiting_status.can_be_passenger = True
    visiting_status.save(update_fields=["can_be_pilot", "can_be_passenger"])
    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="test.example.com",
        club_abbreviation="TC",
        visiting_pilot_enabled=False,
        visiting_pilot_status="Affiliate Member",
    )

    disallowed_towpilot = User.objects.create_user(
        username="disallowed-towpilot",
        first_name="Disallowed",
        last_name="TowPilot",
        membership_status="Affiliate Member",
        towpilot=True,
    )
    eligible_towpilot = User.objects.create_user(
        username="eligible-towpilot",
        first_name="Eligible",
        last_name="TowPilot",
        membership_status="Full Member",
        towpilot=True,
    )

    # Mirrors add_flight's initial={"tow_pilot": logsheet.tow_pilot_id}.
    form = FlightForm(initial={"tow_pilot": disallowed_towpilot.pk}, logsheet=logsheet)
    # The preselection value is still carried (so the widget can render the
    # default) ...
    assert form.initial.get("tow_pilot") == disallowed_towpilot.pk
    # ... but the disallowed member is NOT made selectable / submittable.
    assert disallowed_towpilot.pk not in form.fields["tow_pilot"].queryset.values_list(
        "pk", flat=True
    ), "an initial value must not make a disallowed member selectable"
    with pytest.raises(ValidationError):
        form.fields["tow_pilot"].clean(disallowed_towpilot.pk)

    # An otherwise-eligible initial value still preselects and is selectable.
    form2 = FlightForm(initial={"tow_pilot": eligible_towpilot.pk}, logsheet=logsheet)
    assert eligible_towpilot.pk in form2.fields["tow_pilot"].queryset.values_list(
        "pk", flat=True
    )
    form2.fields["tow_pilot"].clean(eligible_towpilot.pk)
