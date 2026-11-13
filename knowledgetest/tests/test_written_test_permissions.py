"""Written-test compatibility grants require an active account and membership."""

import pytest
from django.contrib.auth import get_user_model

from knowledgetest.permissions import has_written_test_admin_access
from siteconfig.models import MembershipStatus


@pytest.mark.django_db
@pytest.mark.parametrize("grant", ["is_superuser", "webmaster", "preview_cfi"])
def test_disabled_account_cannot_use_written_test_compatibility(grant):
    member = get_user_model().objects.create_user(username=f"disabled-written-{grant}")
    if grant == "preview_cfi":
        member._role_preview_group_name = "Chief Flight Instructor"
    else:
        setattr(member, grant, True)
    member.is_active = False
    assert not has_written_test_admin_access(member)


@pytest.mark.django_db
@pytest.mark.parametrize("grant", ["webmaster", "preview_cfi"])
def test_inactive_membership_cannot_use_written_test_compatibility(grant):
    member = get_user_model().objects.create_user(username=f"nonmember-written-{grant}")
    if grant == "preview_cfi":
        member._role_preview_group_name = "Chief Flight Instructor"
    else:
        member.webmaster = True
    member.membership_status = "Not an active status"
    assert not has_written_test_admin_access(member)


@pytest.mark.django_db
def test_active_member_webmaster_keeps_written_test_access():
    MembershipStatus.objects.get_or_create(
        name="Full Member", defaults={"is_active": True}
    )
    member = get_user_model().objects.create_user(
        username="active-written-webmaster", membership_status="Full Member"
    )
    member.webmaster = True
    assert has_written_test_admin_access(member)
