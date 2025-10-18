import pytest
from django.contrib.auth import get_user_model

from members.constants import ALLOWED_MEMBERSHIP_STATUSES
from members.utils import is_active_member

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
    u = User.objects.create_user(
        username="m1", password="x", membership_status=ALLOWED_MEMBERSHIP_STATUSES[0]
    )
    assert is_active_member(u)


@pytest.mark.django_db
def test_member_with_unallowed_status_not_active():
    u = User.objects.create_user(
        username="m2", password="x", membership_status="Non-Member"
    )
    assert not is_active_member(u)


@pytest.mark.django_db
def test_allow_superuser_flag_respected():
    u = User.objects.create_user(username="su2", password="x", is_superuser=True)
    assert not is_active_member(u, allow_superuser=False)
