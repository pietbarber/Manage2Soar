import pytest

from members.admin import CustomMemberChangeForm
from members.models import Member


@pytest.mark.django_db
def test_admin_contact_visibility_form_can_restore_legacy_redaction():
    member = Member.objects.create_user(
        username="admin-privacy-member",
        email="member@example.com",
        redact_contact=True,
    )

    form = CustomMemberChangeForm(
        data={
            "username": member.username,
            "email": member.email,
            "contact_visibility_email": "inherit",
            "contact_visibility_phone": "inherit",
            "contact_visibility_address": "inherit",
        },
        instance=member,
    )

    assert form.is_valid(), form.errors
    form.save()

    member.refresh_from_db()
    assert not member.redact_contact
    assert member.contact_visibility == {}


@pytest.mark.django_db
def test_admin_contact_visibility_form_sets_per_field_preferences():
    member = Member.objects.create_user(username="admin-privacy-member-2")

    form = CustomMemberChangeForm(
        data={
            "username": member.username,
            "email": member.email,
            "contact_visibility_email": "share",
            "contact_visibility_phone": "hide",
            "contact_visibility_address": "inherit",
        },
        instance=member,
    )

    assert form.is_valid(), form.errors
    form.save()

    member.refresh_from_db()
    assert member.contact_visibility == {"email": "share", "phone": "hide"}
