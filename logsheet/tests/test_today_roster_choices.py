import pytest
from django.contrib.auth import get_user_model

from duty_roster.models import GliderReservation
from logsheet.forms import FlightForm
from logsheet.models import Flight
from siteconfig.models import MembershipStatus, SiteConfiguration


def _choice_groups(field):
    return {
        label: dict(options)
        for label, options in field.choices
        if isinstance(label, str) and isinstance(options, (list, tuple))
    }


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
    assert (
        former_member.pk
        in _choice_groups(form.fields["passenger"])["Not Active Members"]
    )
