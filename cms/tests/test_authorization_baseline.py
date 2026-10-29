"""Characterization tests for the pre-resolver CMS authorization behavior."""

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory
from django.urls import reverse

from cms.admin import PageAdmin
from cms.models import Page, PageMemberPermission, PageRolePermission
from cms.views import can_create_in_directory, can_edit_page
from members.models import Member


@pytest.fixture
def principals(db):
    def make(username, **kwargs):
        return Member.objects.create_user(
            username=username,
            password="pass",
            membership_status=kwargs.pop("membership_status", "Full Member"),
            **kwargs,
        )

    return {
        "anonymous": AnonymousUser(),
        "inactive": make("baseline-inactive", membership_status="Non-Member"),
        "member": make("baseline-member"),
        "director": make("baseline-director", director=True),
        "webmaster": make("baseline-webmaster", webmaster=True),
        "superuser": make("baseline-superuser", is_staff=True, is_superuser=True),
        "kiosk": make("baseline-kiosk", membership_status="Non-Member"),
        "editor": make("baseline-editor"),
    }


@pytest.fixture
def pages(db):
    public = Page.objects.create(title="Public", slug="baseline-public")
    private = Page.objects.create(
        title="Private", slug="baseline-private", is_public=False
    )
    restricted = Page.objects.create(
        title="Restricted", slug="baseline-restricted", is_public=False
    )
    PageRolePermission.objects.create(page=restricted, role_name="director")
    return {"public": public, "private": private, "restricted": restricted}


def kiosk_request(user):
    request = RequestFactory().get("/")
    request.user = user
    request.session = {"is_kiosk_authenticated": True}
    return request


@pytest.mark.django_db
@pytest.mark.parametrize(
    "page_name, principal, expected",
    [
        ("public", "anonymous", True),
        ("public", "inactive", True),
        ("private", "anonymous", False),
        ("private", "inactive", False),
        ("private", "member", True),
        ("restricted", "member", False),
        ("restricted", "director", True),
    ],
)
def test_page_view_baseline(pages, principals, page_name, principal, expected):
    assert pages[page_name].can_user_access(principals[principal]) is expected


@pytest.mark.django_db
def test_private_page_role_rows_use_or_semantics(pages, principals):
    page = pages["restricted"]
    PageRolePermission.objects.create(page=page, role_name="treasurer")
    principals["member"].treasurer = True
    principals["member"].save(update_fields=["treasurer"])

    assert page.can_user_access(principals["member"]) is True


@pytest.mark.django_db
def test_editor_grant_implies_view_on_private_page_but_not_edit_for_everyone(
    pages, principals
):
    page = pages["restricted"]
    PageMemberPermission.objects.create(page=page, member=principals["editor"])

    assert page.can_user_access(principals["editor"]) is True
    assert page.can_user_edit(principals["editor"]) is True
    assert page.can_user_edit(principals["member"]) is False


@pytest.mark.django_db
def test_member_editor_can_edit_public_page_without_changing_visibility(
    pages, principals
):
    page = pages["public"]
    PageMemberPermission.objects.create(page=page, member=principals["editor"])
    assert page.is_public is True
    assert can_edit_page(principals["editor"], page) is True


@pytest.mark.django_db
def test_kiosk_request_bypasses_membership_only_for_page_view(pages, principals):
    kiosk = principals["kiosk"]
    assert pages["private"].can_user_access(kiosk) is False
    assert pages["private"].can_user_access(kiosk, kiosk_request(kiosk)) is True
    assert pages["restricted"].can_user_access(kiosk, kiosk_request(kiosk)) is False


@pytest.mark.django_db
@pytest.mark.parametrize(
    "page_name, principal, expected",
    [
        ("public", "anonymous", False),
        ("public", "member", False),
        ("public", "director", True),
        ("private", "member", False),
        ("private", "director", True),
        ("restricted", "director", True),
        ("restricted", "editor", False),
        ("public", "webmaster", True),
        ("private", "superuser", True),
    ],
)
def test_page_edit_baseline(pages, principals, page_name, principal, expected):
    assert can_edit_page(principals[principal], pages[page_name]) is expected


@pytest.mark.django_db
def test_create_baseline_is_webmaster_only_at_root_and_parent_edit_under_directory(
    pages, principals
):
    assert can_create_in_directory(principals["member"], None) is False
    assert can_create_in_directory(principals["webmaster"], None) is True
    assert can_create_in_directory(principals["member"], pages["public"]) is False
    assert can_create_in_directory(principals["director"], pages["public"]) is True


@pytest.mark.django_db
@pytest.mark.parametrize(
    "page_name, principal, expected_status",
    [
        ("public", "anonymous", 200),
        ("private", "anonymous", 302),
        ("private", "member", 200),
        ("restricted", "member", 302),
        ("restricted", "director", 200),
    ],
)
def test_page_route_statuses(
    client, pages, principals, page_name, principal, expected_status
):
    user = principals[principal]
    if getattr(user, "is_authenticated", False):
        client.force_login(user)
    response = client.get(pages[page_name].get_absolute_url())
    assert response.status_code == expected_status


@pytest.mark.django_db
def test_kiosk_page_route_uses_session_membership_bypass(client, pages, principals):
    client.force_login(principals["kiosk"])
    session = client.session
    session["is_kiosk_authenticated"] = True
    session.save()
    assert client.get(pages["private"].get_absolute_url()).status_code == 200


@pytest.mark.django_db
@pytest.mark.parametrize(
    "principal, expected_status",
    [("anonymous", 302), ("member", 403), ("director", 200), ("editor", 200)],
)
def test_edit_route_statuses(client, pages, principals, principal, expected_status):
    if principal != "anonymous":
        client.force_login(principals[principal])
    PageMemberPermission.objects.get_or_create(
        page=pages["private"], member=principals["editor"]
    )
    response = client.get(reverse("cms:edit_page", args=[pages["private"].pk]))
    assert response.status_code == expected_status


@pytest.mark.django_db
def test_private_ancestor_blocks_public_child_route(client, pages, principals):
    parent = Page.objects.create(
        title="Private parent", slug="baseline-parent", is_public=False
    )
    PageRolePermission.objects.create(page=parent, role_name="director")
    child = Page.objects.create(
        title="Public child", slug="baseline-child", parent=parent, is_public=True
    )
    client.force_login(principals["member"])
    assert client.get(child.get_absolute_url()).status_code == 302
    client.force_login(principals["director"])
    assert client.get(child.get_absolute_url()).status_code == 200


@pytest.mark.django_db
def test_page_admin_change_uses_page_editor_logic_without_membership_gate(
    pages, principals
):
    admin = PageAdmin(Page, AdminSite())
    request = RequestFactory().get("/admin/")
    request.user = principals["editor"]
    PageMemberPermission.objects.create(page=pages["private"], member=request.user)
    assert admin.has_change_permission(request, pages["private"]) is True


@pytest.mark.django_db
def test_page_admin_navbar_fields_are_readonly_except_webmaster_or_superuser(
    principals, pages
):
    admin = PageAdmin(Page, AdminSite())
    request = RequestFactory().get("/admin/")
    request.user = principals["director"]
    assert set(admin.get_readonly_fields(request, pages["public"])) >= {
        "promote_to_navbar",
        "navbar_title",
        "navbar_rank",
    }
    request.user = principals["webmaster"]
    assert not set(admin.get_readonly_fields(request, pages["public"])) & {
        "promote_to_navbar",
        "navbar_title",
        "navbar_rank",
    }
