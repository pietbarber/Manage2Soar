import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from members.utils import is_active_member
from members.utils.membership import get_active_membership_statuses
from siteconfig.models import MembershipStatus

User = get_user_model()


@pytest.mark.django_db
def test_anonymous_not_active():
    assert not is_active_member(None)


@pytest.mark.django_db
def test_superuser_active():
    u = User.objects.create_user(username="su", password="x", is_superuser=True)
    assert is_active_member(u)


@pytest.mark.django_db
def test_member_with_allowed_status_active():
    # Create an active membership status first
    MembershipStatus.objects.create(name="Test Active Member", is_active=True)

    u = User.objects.create_user(
        username="m1", password="x", membership_status="Test Active Member"
    )
    assert is_active_member(u)


@pytest.mark.django_db
def test_member_with_unallowed_status_not_active():
    # Create an inactive membership status
    MembershipStatus.objects.create(name="Test Inactive Member", is_active=False)

    u = User.objects.create_user(
        username="m2", password="x", membership_status="Test Inactive Member"
    )
    assert not is_active_member(u)


@pytest.mark.django_db
def test_allow_superuser_flag_respected():
    u = User.objects.create_user(username="su2", password="x", is_superuser=True)
    assert not is_active_member(u, allow_superuser=False)


@pytest.mark.django_db
def test_get_active_membership_statuses():
    """Test the get_active_membership_statuses utility function."""
    # Create test statuses
    MembershipStatus.objects.create(name="Active Status 1", is_active=True)
    MembershipStatus.objects.create(name="Active Status 2", is_active=True)
    MembershipStatus.objects.create(name="Inactive Status", is_active=False)

    active_statuses = get_active_membership_statuses()

    assert "Active Status 1" in active_statuses
    assert "Active Status 2" in active_statuses
    assert "Inactive Status" not in active_statuses


@pytest.mark.django_db(transaction=True)
def test_get_active_membership_statuses_empty():
    """Test get_active_membership_statuses when no active statuses exist."""
    # Clear all existing data and create only inactive statuses
    MembershipStatus.objects.all().delete()
    MembershipStatus.objects.create(name="Inactive Status", is_active=False)

    active_statuses = get_active_membership_statuses()

    assert len(active_statuses) == 0


@pytest.mark.django_db
def test_dynamic_membership_status_changes():
    """Test that membership status changes are reflected immediately."""
    # Create a status that starts as active
    status = MembershipStatus.objects.create(name="Dynamic Status", is_active=True)

    # Create a user with this status
    user = User.objects.create_user(
        username="dynamic_user", password="x", membership_status="Dynamic Status"
    )

    # Should be active initially
    assert is_active_member(user)

    # Change status to inactive
    status.is_active = False
    status.save()

    # Should now be inactive
    assert not is_active_member(user)


@pytest.mark.django_db
def test_membership_status_deletion_integration():
    """Test the integration between membership status deletion protection and member access."""
    # Create a status and member
    status = MembershipStatus.objects.create(name="Protected Status", is_active=True)
    member = User.objects.create_user(
        username="protected_member", password="x", membership_status="Protected Status"
    )

    # Member should be active initially
    assert is_active_member(member)

    # Try to delete status - should be protected
    with pytest.raises(ValidationError):
        status.delete()

    # Status still exists, member still active
    assert MembershipStatus.objects.filter(name="Protected Status").exists()
    assert is_active_member(member)

    # Change member to different status, then deletion should work
    member.membership_status = "Another Status"
    member.save()

    # Now deletion should succeed (no members using it)
    status.delete()
    assert not MembershipStatus.objects.filter(name="Protected Status").exists()
