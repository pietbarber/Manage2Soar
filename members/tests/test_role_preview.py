import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse

from cms.models import Page
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
def preview_page(db):
    return Page.objects.create(
        title="Role Preview Page",
        slug="role-preview-page",
        is_public=True,
    )


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
