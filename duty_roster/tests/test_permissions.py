from datetime import date

import pytest
from django.contrib.auth.models import Group
from django.urls import reverse

from duty_roster.models import DutyAssignment
from duty_roster.permissions import (
    has_all_swap_requests_access,
    has_duty_delinquents_access,
    has_rostermeister_access,
)
from members.models import Member
from siteconfig.models import MembershipStatus


@pytest.fixture
def active_status(db):
    return MembershipStatus.objects.create(name="Duty Active", is_active=True)


@pytest.mark.django_db
def test_duty_delinquent_access_requires_active_account_and_membership(active_status):
    member = Member.objects.create_user(
        username="inactive-duty-viewer", membership_status=active_status.name
    )
    member.rostermeister = True
    member.save()
    assert has_duty_delinquents_access(member)

    member.is_active = False
    assert not has_duty_delinquents_access(member)

    member.is_active = True
    member.membership_status = "Inactive Duty Status"
    assert not has_duty_delinquents_access(member)


@pytest.mark.django_db
def test_staff_alone_cannot_view_all_swap_requests(active_status):
    member = Member.objects.create_user(
        username="staff-swap-viewer",
        membership_status=active_status.name,
        is_staff=True,
    )
    assert not has_all_swap_requests_access(member)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("group_name", "expected"),
    [
        ("Directors", False),
        ("Secretary", True),
        ("Treasurer", True),
        ("Member Managers", True),
        ("Instructor Admins", True),
        ("Rostermeisters", True),
    ],
)
def test_all_swap_requests_access_matches_registered_role_capability(
    active_status, group_name, expected
):
    member = Member.objects.create_user(
        username=f"{group_name.lower().replace(' ', '-')}-swap-viewer",
        membership_status=active_status.name,
    )
    member.groups.add(Group.objects.get(name=group_name))

    assert has_all_swap_requests_access(member) is expected


@pytest.mark.django_db
def test_superuser_keeps_all_swap_requests_access(active_status):
    member = Member.objects.create_user(
        username="superuser-swap-viewer",
        membership_status=active_status.name,
        is_superuser=True,
    )

    assert has_all_swap_requests_access(member)


def _assignment_form_url(day):
    return reverse(
        "duty_roster:assignment_edit_form",
        kwargs={"year": day.year, "month": day.month, "day": day.day},
    )


@pytest.mark.django_db
def test_inactive_rostermeister_cannot_read_assignment_edit_form(client, active_status):
    member = Member.objects.create_user(
        username="inactive-assignment-reader",
        membership_status=active_status.name,
        is_active=False,
        rostermeister=True,
    )
    day = date(2030, 1, 2)
    client.force_login(member)

    response = client.get(_assignment_form_url(day))

    assert response.status_code == 403
    assert not DutyAssignment.objects.filter(date=day).exists()


@pytest.mark.django_db
def test_inactive_rostermeister_cannot_mutate_assignment_edit_form(
    client, active_status
):
    member = Member.objects.create_user(
        username="inactive-assignment-writer",
        membership_status=active_status.name,
        is_active=False,
        rostermeister=True,
        instructor=True,
    )
    day = date(2030, 1, 3)
    assignment = DutyAssignment.objects.create(date=day)
    client.force_login(member)

    response = client.post(
        reverse(
            "duty_roster:assignment_save_form",
            kwargs={"year": day.year, "month": day.month, "day": day.day},
        ),
        {"instructor": member.pk},
    )

    assignment.refresh_from_db()
    assert response.status_code == 403
    assert assignment.instructor_id is None


@pytest.mark.django_db
def test_active_rostermeister_can_read_and_mutate_assignment_edit_form(
    client, active_status
):
    member = Member.objects.create_user(
        username="active-assignment-editor",
        membership_status=active_status.name,
        rostermeister=True,
        instructor=True,
    )
    day = date(2030, 1, 4)
    client.force_login(member)

    read_response = client.get(_assignment_form_url(day))
    save_response = client.post(
        reverse(
            "duty_roster:assignment_save_form",
            kwargs={"year": day.year, "month": day.month, "day": day.day},
        ),
        {"instructor": member.pk},
    )

    assert read_response.status_code == 200
    assert save_response.status_code == 200
    assert DutyAssignment.objects.get(date=day).instructor_id == member.pk


@pytest.mark.django_db
def test_active_superuser_can_access_assignment_edit_form(client, active_status):
    member = Member.objects.create_superuser(
        username="active-assignment-superuser",
        email="active-assignment-superuser@example.com",
        password="testpass123",
    )
    member.membership_status = active_status.name
    member.save(update_fields=["membership_status"])
    client.force_login(member)

    response = client.get(_assignment_form_url(date(2030, 1, 5)))

    assert response.status_code == 200
    assert has_rostermeister_access(member)
