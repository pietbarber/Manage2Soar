from unittest.mock import MagicMock, patch

import pytest
from django.contrib.admin.sites import AdminSite

from members.admin import CustomMemberCreationForm, MemberAdmin
from members.models import Member


@pytest.mark.django_db
def test_admin_creation_form_allows_passwordless_member_with_setup_email():
    form = CustomMemberCreationForm(
        data={
            "username": "newpilot",
            "email": "newpilot@example.com",
            "first_name": "New",
            "last_name": "Pilot",
            "password1": "",
            "password2": "",
            "send_account_setup_email": True,
        }
    )

    assert form.is_valid(), form.errors
    member = form.save()
    assert not member.has_usable_password()


@pytest.mark.django_db
def test_admin_creation_form_preserves_supplied_password():
    form = CustomMemberCreationForm(
        data={
            "username": "passwordpilot",
            "email": "passwordpilot@example.com",
            "first_name": "Password",
            "last_name": "Pilot",
            "password1": "A-strong-admin-password-979",
            "password2": "A-strong-admin-password-979",
            "send_account_setup_email": False,
        }
    )

    assert form.is_valid(), form.errors
    member = form.save()
    assert member.check_password("A-strong-admin-password-979")


@pytest.mark.django_db
def test_admin_sends_setup_email_only_when_creating_member(
    django_capture_on_commit_callbacks,
):
    form = CustomMemberCreationForm(
        data={
            "username": "newpilot",
            "email": "newpilot@example.com",
            "first_name": "New",
            "last_name": "Pilot",
            "password1": "",
            "password2": "",
            "send_account_setup_email": True,
        }
    )
    assert form.is_valid(), form.errors
    member = form.save(commit=False)
    member_admin = MemberAdmin(Member, AdminSite())

    with patch("members.admin.send_account_setup_email") as send_email:
        with django_capture_on_commit_callbacks(execute=True):
            member_admin.save_model(MagicMock(), member, form, change=False)
            send_email.assert_not_called()
        send_email.assert_called_once_with(member)

        member_admin.save_model(MagicMock(), member, form, change=True)
        send_email.assert_called_once_with(member)


@pytest.mark.django_db
def test_admin_does_not_send_setup_email_when_option_is_unchecked(
    django_capture_on_commit_callbacks,
):
    form = CustomMemberCreationForm(
        data={
            "username": "noinvite",
            "email": "noinvite@example.com",
            "first_name": "No",
            "last_name": "Invite",
            "password1": "A-strong-admin-password-979",
            "password2": "A-strong-admin-password-979",
            "send_account_setup_email": False,
        }
    )
    assert form.is_valid(), form.errors
    member = form.save(commit=False)
    member_admin = MemberAdmin(Member, AdminSite())

    with patch("members.admin.send_account_setup_email") as send_email:
        with django_capture_on_commit_callbacks(execute=True):
            member_admin.save_model(MagicMock(), member, form, change=False)
        send_email.assert_not_called()


@pytest.mark.django_db
def test_admin_creation_form_requires_email_when_sending_setup_email():
    form = CustomMemberCreationForm(
        data={
            "username": "newpilot",
            "email": "",
            "first_name": "New",
            "last_name": "Pilot",
            "password1": "",
            "password2": "",
            "send_account_setup_email": True,
        }
    )

    assert not form.is_valid()
    assert "email" in form.errors
