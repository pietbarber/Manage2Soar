import pytest

from cms.models import Page, PageMemberPermission
from cms.permissions import has_cms_edit_access, has_cms_view_access
from members.models import Member
from members.utils.membership import clear_active_membership_statuses_cache
from siteconfig.models import MembershipStatus


@pytest.mark.django_db
def test_cms_capabilities_require_active_account_and_membership():
    status = MembershipStatus.objects.create(name="CMS Active", is_active=True)
    member = Member.objects.create_user(
        username="cms-inactive", membership_status=status.name
    )
    permission = "cms.view_page"
    page_permission = member.user_permissions
    from django.contrib.auth.models import Permission

    page_permission.add(
        Permission.objects.get(
            content_type__app_label="cms",
            content_type__model="page",
            codename=permission.split(".")[1],
        )
    )
    assert has_cms_view_access(member)

    member.is_active = False
    assert not has_cms_view_access(member)
    assert not has_cms_edit_access(member)


@pytest.mark.django_db
def test_private_page_editor_must_still_be_active():
    status = MembershipStatus.objects.create(name="CMS Editor Active", is_active=True)
    clear_active_membership_statuses_cache()
    member = Member.objects.create_user(
        username="private-page-editor", membership_status=status.name
    )
    page = Page.objects.create(title="Private", slug="private", is_public=False)
    PageMemberPermission.objects.create(page=page, member=member)
    assert page.can_user_access(member)

    member.is_active = False
    assert not page.can_user_access(member)
