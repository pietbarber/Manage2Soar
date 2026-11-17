import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.urls import reverse

from instructors.models import SyllabusDocument
from members.models import Member
from siteconfig.models import MembershipStatus


@pytest.mark.django_db
def test_record_only_permission_cannot_edit_syllabus_document(client):
    MembershipStatus.objects.create(name="Syllabus active", is_active=True)
    user = get_user_model().objects.create_user(
        username="record-only-syllabus",
        password="test-password",
        membership_status="Syllabus active",
    )
    record_permission = Permission.objects.get(
        content_type__app_label="instructors",
        codename="can_record_instruction",
    )
    user.user_permissions.add(record_permission)
    document = SyllabusDocument.objects.create(
        slug="header", title="Header", content="Original content"
    )
    client.force_login(user)

    overview = client.get(reverse("instructors:syllabus_overview"))
    response = client.post(
        reverse("instructors:edit_syllabus_document", args=[document.slug]),
        {"slug": document.slug, "title": "Changed", "content": "Changed content"},
    )

    assert overview.status_code == 403
    assert response.status_code == 403
    document.refresh_from_db()
    assert document.title == "Header"
    assert document.content == "Original content"


@pytest.mark.django_db
@pytest.mark.parametrize("grant", ["model_permission", "legacy_instructor"])
def test_syllabus_document_edit_keeps_explicit_and_legacy_access(client, grant):
    MembershipStatus.objects.create(name="Syllabus editor active", is_active=True)
    user = Member.objects.create_user(
        username=f"syllabus-editor-{grant}",
        password="test-password",
        membership_status="Syllabus editor active",
        instructor=grant == "legacy_instructor",
    )
    if grant == "model_permission":
        permission = Permission.objects.get(
            content_type__app_label="instructors",
            codename="change_syllabusdocument",
        )
        user.user_permissions.add(permission)
    document = SyllabusDocument.objects.create(
        slug=f"header-{grant}", title="Header", content="Original content"
    )
    client.force_login(user)

    response = client.post(
        reverse("instructors:edit_syllabus_document", args=[document.slug]),
        {"slug": document.slug, "title": "Changed", "content": "Changed content"},
    )

    assert response.status_code == 302
    document.refresh_from_db()
    assert document.title == "Changed"
    assert document.content == "Changed content"
