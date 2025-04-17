import pytest
from members.models import Member
from members.pipeline import (
    create_username,
    set_default_membership_status,
)

@pytest.mark.django_db
def test_create_username_from_names():
    details = {"first_name": "Piet", "last_name": "Barber", "nickname": ""}
    result = create_username(None, details, backend=None)
    assert "username" in result
    assert result["username"].startswith("piet.barber")

@pytest.mark.django_db
def test_create_username_uses_nickname():
    details = {"first_name": "Piet", "last_name": "Barber", "nickname": "PB"}
    result = create_username(None, details, backend=None)
    assert result["username"].startswith("pb.barber")

@pytest.mark.django_db
def test_create_username_fallback_to_email():
    details = {"first_name": "", "last_name": "", "email": "sally@example.com"}
    result = create_username(None, details, backend=None)
    assert result["username"].startswith("sally")

@pytest.mark.django_db
def test_set_default_membership_status_sets_pending():
    user = Member.objects.create(username="testuser", membership_status="")
    set_default_membership_status(None, user)
    user.save()  # ✅ Save the updated status
    user.refresh_from_db()
    assert user.membership_status == "Pending"