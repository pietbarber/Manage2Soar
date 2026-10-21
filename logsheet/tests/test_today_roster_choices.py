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
