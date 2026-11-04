import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.urls import reverse

from members.models import Member
from siteconfig.models import MembershipStatus


def _password_change_url(member):
    return reverse("admin:auth_user_password_change", args=[member.pk])


def _make_limited_editor():
    MembershipStatus.objects.get_or_create(
        name="Full Member", defaults={"is_active": True}
    )
    editor = get_user_model().objects.create_user(
        username="limited-password-editor",
        password="editor-password",
        is_staff=True,
        membership_status="Full Member",
    )
    editor.user_permissions.add(
        Permission.objects.get(
            content_type__app_label="members", codename="change_member"
        )
    )
    return editor


def _force_admin_login(client, user):
    client.force_login(user, backend="django.contrib.auth.backends.ModelBackend")


@pytest.mark.django_db
def test_limited_member_editor_cannot_get_another_members_password_change_form(
    client,
):
    editor = _make_limited_editor()
    target = Member.objects.create_user(
        username="password-change-target", password="old-password"
    )
    _force_admin_login(client, editor)

    response = client.get(_password_change_url(target))

    assert response.status_code == 403


@pytest.mark.django_db
def test_limited_member_editor_cannot_post_password_change_for_privileged_member(
    client,
):
    editor = _make_limited_editor()
    target = Member.objects.create_superuser(
        username="privileged-password-target", password="old-password"
    )
    _force_admin_login(client, editor)

    response = client.post(
        _password_change_url(target),
        {
            "password1": "A-strong-admin-password-979",
            "password2": "A-strong-admin-password-979",
            "usable_password": "true",
        },
    )

    assert response.status_code == 403
    target.refresh_from_db()
    assert target.check_password("old-password")


@pytest.mark.django_db
def test_limited_member_editor_can_change_own_password(client):
    editor = _make_limited_editor()
    _force_admin_login(client, editor)

    response = client.post(
        _password_change_url(editor),
        {
            "password1": "A-strong-admin-password-979",
            "password2": "A-strong-admin-password-979",
            "usable_password": "true",
        },
    )

    assert response.status_code == 302
    editor.refresh_from_db()
    assert editor.check_password("A-strong-admin-password-979")


@pytest.mark.django_db
def test_superuser_can_get_and_post_another_members_password_change_form(client):
    superuser = get_user_model().objects.create_superuser(
        username="password-change-superuser", password="admin-password"
    )
    target = Member.objects.create_user(
        username="superuser-password-target", password="old-password"
    )
    _force_admin_login(client, superuser)
    url = _password_change_url(target)

    assert client.get(url).status_code == 200
    response = client.post(
        url,
        {
            "password1": "A-strong-admin-password-979",
            "password2": "A-strong-admin-password-979",
            "usable_password": "true",
        },
    )

    assert response.status_code == 302
    target.refresh_from_db()
    assert target.check_password("A-strong-admin-password-979")
