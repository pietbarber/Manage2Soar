import pytest
from django.contrib.auth import get_user_model

from members.models import Member
from members.utils import can_view_personal_info


User = get_user_model()


@pytest.mark.django_db
def test_redact_contact_default_false():
    m = Member.objects.create(username="rtest", email="rtest@example.com")
    assert not m.redact_contact


@pytest.mark.django_db
def test_can_view_personal_info_anonymous_and_normal_member():
    subject = Member.objects.create(
        username="subj", email="subj@example.com", redact_contact=True)
    anon = None
    assert not can_view_personal_info(anon, subject)

    viewer = Member.objects.create(username="viewer", email="viewer@example.com")
    assert not can_view_personal_info(viewer, subject)


@pytest.mark.django_db
def test_can_view_personal_info_privileged_superuser():
    subject = Member.objects.create(
        username="subj2", email="s2@example.com", redact_contact=True)
    admin = User.objects.create(username="admin", is_superuser=True, is_staff=True)
    assert can_view_personal_info(admin, subject)


@pytest.mark.django_db
def test_can_view_personal_info_group_exempt(settings):
    # Ensure group exemption setting works
    settings.MEMBERS_REDACT_EXEMPT_GROUPS = ["Webmasters"]
    subj = Member.objects.create(
        username="subj3", email="s3@example.com", redact_contact=True)
    viewer = Member.objects.create(username="wm", email="wm@example.com")
    gp = viewer.groups.create(name="Webmasters")
    assert can_view_personal_info(viewer, subj)
