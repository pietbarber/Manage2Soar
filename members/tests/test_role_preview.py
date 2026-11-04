import logging

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import override_settings
from django.urls import reverse

from cms.models import Page
from members.authorization import has_role_admin_access
from members.models import RoleMetadata

User = get_user_model()


@pytest.fixture
def preview_admin(db):
    return User.objects.create_superuser(
        username="role-preview-admin",
        password="test-password",
        email="preview@example.com",
    )


@pytest.fixture
def role_admin(db):
    group, _ = Group.objects.get_or_create(name="Member Managers")
    metadata, _ = RoleMetadata.objects.get_or_create(
        group=group,
        defaults={
            "key": "member_managers_preview_test",
            "display_name": "Member Managers",
        },
    )
    RoleMetadata.objects.filter(pk=metadata.pk).update(admin_access=True)
    member = User.objects.create_user(
        username="role-preview-member-manager",
        password="test-password",
        member_manager=True,
        is_staff=True,
    )
    member.groups.add(group)
    return member


@pytest.fixture
def preview_page(db):
    return Page.objects.create(
        title="Role Preview Page",
        slug="role-preview-page",
        is_public=True,
    )


@pytest.mark.django_db
@override_settings(DEBUG=True)
def test_role_admin_cannot_start_or_control_preview(client, role_admin, preview_page):
    client.force_login(role_admin)
    assert has_role_admin_access(role_admin)

    assert client.get(reverse("members:role_preview")).status_code == 403

    response = client.post(
        reverse("members:role_preview_start"),
        {"role_key": "directors"},
    )
    assert response.status_code == 403
    assert client.session.get("role_preview") is None

    # A stale/injected state must not activate role projection for a role
    # holder, and the role holder must not be able to clear it through the
    # preview control endpoint either.
    session = client.session
    session["role_preview"] = {"role_key": "directors", "debug": False}
    session.save()
    response = client.get(reverse("cms:cms_page", kwargs={"path": preview_page.slug}))
    assert response.status_code == 200
    assert response.context["role_preview"] is None

    response = client.post(reverse("members:role_preview_stop"))
    assert response.status_code == 403
    assert client.session["role_preview"]["role_key"] == "directors"


@pytest.mark.django_db
def test_superuser_can_start_and_control_role_preview(client, preview_admin):
    client.force_login(preview_admin)

    assert client.get(reverse("members:role_preview")).status_code == 200
    response = client.post(
        reverse("members:role_preview_start"),
        {"role_key": "directors"},
    )
    assert response.status_code == 302
    assert client.session["role_preview"]["role_key"] == "directors"

    response = client.post(reverse("members:role_preview_stop"))
    assert response.status_code == 302
    assert client.session.get("role_preview") is None


@pytest.mark.django_db
@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    }
)
def test_role_preview_projects_capabilities_and_reports_cms_edit_access(
    client, preview_admin, preview_page
):
    client.force_login(preview_admin)

    response = client.post(
        reverse("members:role_preview_start"),
        {"role_key": "directors"},
    )

    assert response.status_code == 302
    response = client.get(reverse("cms:cms_page", kwargs={"path": preview_page.slug}))

    assert response.status_code == 200
    assert response.context["role_preview_edit_diagnostic"] == (True, True)
    assert (
        response.context["role_preview"]["display_name"]
        == RoleMetadata.objects.get(key="directors").display_name
    )


@pytest.mark.django_db
def test_normal_role_preview_blocks_mutation(client, preview_admin, preview_page):
    client.force_login(preview_admin)
    client.post(
        reverse("members:role_preview_start"),
        {"role_key": "directors"},
    )

    response = client.post(
        reverse("cms:edit_page", args=[preview_page.pk]),
        {},
    )

    assert response.status_code == 403
    assert b"read-only" in response.content


@pytest.mark.django_db
@override_settings(DEBUG=True)
def test_debug_role_preview_allows_mutation_route(client, preview_admin, preview_page):
    client.force_login(preview_admin)
    client.post(
        reverse("members:role_preview_start"),
        {"role_key": "directors", "debug": "on"},
    )

    response = client.post(
        reverse("cms:edit_page", args=[preview_page.pk]),
        {},
    )

    assert response.status_code != 403


@pytest.mark.django_db
def test_role_preview_can_be_stopped(client, preview_admin):
    client.force_login(preview_admin)
    client.post(
        reverse("members:role_preview_start"),
        {"role_key": "directors"},
    )

    response = client.post(reverse("members:role_preview_stop"))

    assert response.status_code == 302
    assert client.session.get("role_preview") is None


@pytest.mark.django_db
def test_role_preview_management_page_remains_accessible_while_active(
    client, preview_admin
):
    client.force_login(preview_admin)
    client.post(
        reverse("members:role_preview_start"),
        {"role_key": "directors"},
    )

    response = client.get(reverse("members:role_preview"))

    assert response.status_code == 200
    assert b"Exit preview" in response.content


@pytest.mark.django_db
def test_stale_role_preview_session_is_not_cleared_by_get(client, preview_admin):
    client.force_login(preview_admin)
    session = client.session
    stale_state = {"role_key": "role-that-no-longer-exists", "debug": False}
    session["role_preview"] = stale_state
    session.save()

    response = client.get(reverse("members:role_preview"))

    assert response.status_code == 200
    assert client.session["role_preview"] == stale_state


@pytest.mark.django_db
def test_role_preview_logs_structured_start_stop_rejected_and_blocked_events(
    client, preview_admin, preview_page, caplog
):
    client.force_login(preview_admin)
    caplog.set_level(logging.INFO, logger="members.role_preview")

    client.post(
        reverse("members:role_preview_start"),
        {"role_key": "not-a-role"},
    )
    assert any(
        record.role_preview_outcome == "rejected"
        and record.role_preview_event["reason"] == "unknown_role"
        for record in caplog.records
    )

    client.post(
        reverse("members:role_preview_start"),
        {"role_key": "directors"},
    )
    assert any(record.role_preview_outcome == "start" for record in caplog.records)

    client.post(reverse("cms:edit_page", args=[preview_page.pk]), {})
    assert any(record.role_preview_outcome == "blocked" for record in caplog.records)

    client.post(reverse("members:role_preview_stop"))
    assert any(record.role_preview_outcome == "stop" for record in caplog.records)


@pytest.mark.django_db
@override_settings(DEBUG=False)
def test_debug_session_state_cannot_enable_mutations_when_debug_is_off(
    client, preview_admin, preview_page
):
    client.force_login(preview_admin)
    session = client.session
    session["role_preview"] = {"role_key": "directors", "debug": True}
    session.save()

    response = client.post(
        reverse("cms:edit_page", args=[preview_page.pk]),
        {},
    )

    assert response.status_code == 403
    assert b"read-only" in response.content
    assert client.session["role_preview"]["debug"] is True


@pytest.mark.django_db
@override_settings(DEBUG=False)
def test_debug_preview_cannot_be_started_outside_debug(client, preview_admin):
    client.force_login(preview_admin)
    response = client.post(
        reverse("members:role_preview_start"),
        {"role_key": "directors", "debug": "on"},
    )

    assert response.status_code == 403
