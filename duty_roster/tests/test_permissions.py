import pytest

from duty_roster.permissions import (
    has_all_swap_requests_access,
    has_duty_delinquents_access,
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
