"""
Tests for CMS editing permissions and views.

Tests the new role-based editing permission system added in Issue #273.
"""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import Client, TestCase
from django.urls import reverse

from cms.models import Document, Page, PageMemberPermission, PageRolePermission
from cms.views import can_create_in_directory, can_edit_page

User = get_user_model()


class EditingPermissionFunctionTests(TestCase):
    """Test the permission functions can_edit_page and can_create_in_directory."""

    def setUp(self):
        # Create test pages
        self.public_page = Page.objects.create(
            title="Public Page", slug="public", is_public=True
        )
        self.member_page = Page.objects.create(
            title="Member Page", slug="member", is_public=False
        )
        self.board_page = Page.objects.create(
            title="Board Page", slug="board", is_public=False
        )
        # Add role restriction to board page
        PageRolePermission.objects.create(page=self.board_page, role_name="director")

        # Create test users
        self.anonymous_user = AnonymousUser()  # Proper anonymous user representation
        self.member = User.objects.create_user(
            username="member",
            email="member@test.com",
            membership_status="Full Member",
        )
        self.director = User.objects.create_user(
            username="director",
            email="director@test.com",
            membership_status="Full Member",
        )
        self.director.director = True
        self.director.save()

        self.webmaster = User.objects.create_user(
            username="webmaster",
            email="webmaster@test.com",
            membership_status="Full Member",
        )
        self.webmaster.webmaster = True
        self.webmaster.save()

    def test_can_edit_page_anonymous_user(self):
        """Anonymous users cannot edit any pages."""
        self.assertFalse(can_edit_page(self.anonymous_user, self.public_page))
        self.assertFalse(can_edit_page(self.anonymous_user, self.member_page))
        self.assertFalse(can_edit_page(self.anonymous_user, self.board_page))

    def test_can_edit_page_webmaster_override(self):
        """Webmasters can edit all pages."""
        self.assertTrue(can_edit_page(self.webmaster, self.public_page))
        self.assertTrue(can_edit_page(self.webmaster, self.member_page))
        self.assertTrue(can_edit_page(self.webmaster, self.board_page))

    def test_can_edit_page_public_pages_webmaster_only(self):
        """Only webmasters can edit public pages."""
        self.assertFalse(can_edit_page(self.member, self.public_page))
        self.assertFalse(can_edit_page(self.director, self.public_page))
        self.assertTrue(can_edit_page(self.webmaster, self.public_page))

    def test_can_edit_page_role_restricted_pages(self):
        """Role-restricted pages follow 'token to see = ability to edit' logic."""
        # Member cannot see/edit board page
        self.assertFalse(can_edit_page(self.member, self.board_page))
        # Director can see/edit board page
        self.assertTrue(can_edit_page(self.director, self.board_page))

    def test_can_edit_page_unrestricted_private_pages(self):
        """
        Regular members can VIEW unrestricted private pages, but cannot EDIT them.
        Only officers or members with explicit permissions can edit.
        """
        # First verify they can see the page
        self.assertTrue(self.member_page.can_user_access(self.member))
        self.assertTrue(self.member_page.can_user_access(self.director))

        # Regular member can see but CANNOT edit (no edit permission)
        self.assertFalse(can_edit_page(self.member, self.member_page))

        # Director CAN edit (has officer role)
        self.assertTrue(can_edit_page(self.director, self.member_page))

    def test_can_create_in_directory_anonymous_user(self):
        """Anonymous users cannot create pages."""
        self.assertFalse(can_create_in_directory(self.anonymous_user, None))
        self.assertFalse(can_create_in_directory(self.anonymous_user, self.public_page))

    def test_can_create_in_directory_webmaster_override(self):
        """Webmasters can create pages anywhere."""
        self.assertTrue(can_create_in_directory(self.webmaster, None))
        self.assertTrue(can_create_in_directory(self.webmaster, self.public_page))
        self.assertTrue(can_create_in_directory(self.webmaster, self.board_page))

    def test_can_create_in_directory_public_parent_webmaster_only(self):
        """Only webmasters can create pages under public parents."""
        self.assertFalse(can_create_in_directory(self.member, self.public_page))
        self.assertFalse(can_create_in_directory(self.director, self.public_page))
        self.assertTrue(can_create_in_directory(self.webmaster, self.public_page))

    def test_can_create_in_directory_role_restricted_parent(self):
        """Creating under role-restricted parent requires same roles."""
        # Member cannot create under board page
        self.assertFalse(can_create_in_directory(self.member, self.board_page))
        # Director can create under board page
        self.assertTrue(can_create_in_directory(self.director, self.board_page))

    def test_can_create_in_directory_unrestricted_parent(self):
        """
        Regular members can VIEW unrestricted private pages, but cannot EDIT/CREATE under them.
        Only officers (director/secretary/webmaster) or members with explicit permissions can edit.
        """
        # First verify they can see the parent page
        self.assertTrue(self.member_page.can_user_access(self.member))
        self.assertTrue(self.member_page.can_user_access(self.director))

        # Regular member can see but CANNOT create under it (no edit permission)
        self.assertFalse(can_create_in_directory(self.member, self.member_page))

        # Director CAN create under it (has officer role)
        self.assertTrue(can_create_in_directory(self.director, self.member_page))

    def test_can_create_in_directory_root_level(self):
        """Root-level creation (parent=None) is webmaster-only."""
        self.assertFalse(can_create_in_directory(self.member, None))
        self.assertFalse(can_create_in_directory(self.director, None))
        self.assertTrue(can_create_in_directory(self.webmaster, None))


class EditPageViewTests(TestCase):
    """Test the edit_page view with proper permission enforcement."""

    def setUp(self):
        self.client = Client()

        # Create test page
        self.page = Page.objects.create(
            title="Test Page",
            slug="test-page",
            content="<p>Original content</p>",
            is_public=False,
        )

        # Create test users
        self.member = User.objects.create_user(
            username="member",
            email="member@test.com",
            password="testpass123",
            membership_status="Full Member",
        )
        self.webmaster = User.objects.create_user(
            username="webmaster",
            email="webmaster@test.com",
            password="testpass123",
            membership_status="Full Member",
        )
        self.webmaster.webmaster = True
        self.webmaster.save()

        self.director = User.objects.create_user(
            username="director",
            email="director@test.com",
            password="testpass123",
            membership_status="Full Member",
        )
        self.director.director = True
        self.director.save()

    def test_edit_page_requires_authentication(self):
        """Edit page redirects anonymous users to login."""
        url = reverse("cms:edit_page", kwargs={"page_id": self.page.id})
        response = self.client.get(url)
        # @active_member_required redirects anonymous users to login
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    def test_edit_page_permission_denied(self):
        """Edit page denies access to users without permission."""
        # Make page public (only webmasters can edit)
        self.page.is_public = True
        self.page.save()

        self.client.force_login(self.member)
        url = reverse("cms:edit_page", kwargs={"page_id": self.page.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)  # View returns 403, not redirect

    def test_edit_page_permission_granted(self):
        """Edit page allows access to users with edit permission (officers)."""
        self.client.force_login(self.director)
        url = reverse("cms:edit_page", kwargs={"page_id": self.page.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Edit Page")
        self.assertContains(response, self.page.title)

    def test_edit_page_webmaster_can_edit_public(self):
        """Webmasters can edit public pages."""
        self.page.is_public = True
        self.page.save()

        self.client.force_login(self.webmaster)
        url = reverse("cms:edit_page", kwargs={"page_id": self.page.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Edit Page")

    def test_edit_page_post_updates_content(self):
        """POST to edit page updates the page content (requires edit permission)."""
        self.client.force_login(self.director)
        url = reverse("cms:edit_page", kwargs={"page_id": self.page.id})

        form_data = {
            "title": "Updated Title",
            "slug": "updated-page",  # Required field
            "content": "<p>Updated content</p>",
            "is_public": False,
            "documents-TOTAL_FORMS": "0",
            "documents-INITIAL_FORMS": "0",
            "documents-MIN_NUM_FORMS": "0",
            "documents-MAX_NUM_FORMS": "1000",
        }

        response = self.client.post(url, data=form_data)
        # Should redirect after successful save        # Check page was updated
        self.assertEqual(response.status_code, 302)
        self.page.refresh_from_db()
        self.assertEqual(self.page.title, "Updated Title")
        self.assertEqual(self.page.content, "<p>Updated content</p>")

    def test_edit_page_context_variables(self):
        """Edit page includes required context variables."""
        self.client.force_login(self.director)
        url = reverse("cms:edit_page", kwargs={"page_id": self.page.id})
        response = self.client.get(url)

        self.assertIn("page", response.context)
        self.assertIn("form", response.context)
        # Context variable is 'formset', not 'document_formset'
        self.assertIn("formset", response.context)
        self.assertIn("page_title", response.context)
        # can_edit_page is not passed in context - permission check happens in the view


class CreatePageViewTests(TestCase):
    """Test the create_page view with proper permission enforcement."""

    def setUp(self):
        self.client = Client()

        # Create test parent page
        self.parent_page = Page.objects.create(
            title="Parent Page",
            slug="parent",
            is_public=False,
        )

        # Create test users
        self.member = User.objects.create_user(
            username="member",
            email="member@test.com",
            password="testpass123",
            membership_status="Full Member",
        )
        self.webmaster = User.objects.create_user(
            username="webmaster",
            email="webmaster@test.com",
            password="testpass123",
            membership_status="Full Member",
        )
        self.webmaster.webmaster = True
        self.webmaster.save()

        self.director = User.objects.create_user(
            username="director",
            email="director@test.com",
            password="testpass123",
            membership_status="Full Member",
        )
        self.director.director = True
        self.director.save()

    def test_create_page_requires_authentication(self):
        """Create page redirects anonymous users to login."""
        url = reverse("cms:create_page")
        response = self.client.get(url)
        # @active_member_required redirects anonymous users to login
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    def test_create_page_root_level_webmaster_only(self):
        """Only webmasters can create root-level pages."""
        self.client.force_login(self.member)
        url = reverse("cms:create_page")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)  # View returns 403, not redirect

    def test_create_page_webmaster_can_create_root(self):
        """Webmasters can create root-level pages."""
        self.client.force_login(self.webmaster)
        url = reverse("cms:create_page")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Create New CMS Page")  # Actual page title

    def test_create_page_with_parent_permission_check(self):
        """Creating under parent requires permission to access parent."""
        # Make parent public (only webmasters can create under it)
        self.parent_page.is_public = True
        self.parent_page.save()

        self.client.force_login(self.member)
        url = reverse("cms:create_page") + f"?parent={self.parent_page.id}"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)  # View returns 403, not redirect

    def test_create_page_post_creates_new_page(self):
        """
        POST to create page requires EDIT permission on parent.
        Regular members cannot create under unrestricted private pages without explicit permission.
        """
        # Regular member cannot create (no edit permission)
        self.client.force_login(self.member)
        url = reverse("cms:create_page") + f"?parent={self.parent_page.id}"

        form_data = {
            "title": "New Page",
            "slug": "new-page",
            "parent": self.parent_page.id,
            "content": "<p>New content</p>",
            "is_public": False,
            "documents-TOTAL_FORMS": "0",
            "documents-INITIAL_FORMS": "0",
            "documents-MIN_NUM_FORMS": "0",
            "documents-MAX_NUM_FORMS": "1000",
        }

        response = self.client.post(url, data=form_data)
        self.assertEqual(response.status_code, 403)  # Should fail - no edit permission

        # Director CAN create (has officer role)
        self.client.force_login(self.director)
        response = self.client.post(url, data=form_data)
        self.assertEqual(response.status_code, 302)  # Should succeed

        # Check page was created
        new_page = Page.objects.get(slug="new-page")
        self.assertEqual(new_page.title, "New Page")
        self.assertEqual(new_page.parent, self.parent_page)

    def test_create_page_context_variables(self):
        """Create page includes required context variables."""
        # Use webmaster who can create under any parent
        self.client.force_login(self.webmaster)
        url = reverse("cms:create_page") + f"?parent={self.parent_page.id}"
        response = self.client.get(url)

        self.assertIn("form", response.context)
        self.assertIn("formset", response.context)  # Context variable is 'formset'
        self.assertIn("page_title", response.context)
        self.assertEqual(response.context["page_title"], "Create New CMS Page")
        # parent_page and can_create_page are not passed in context - permission check happens in the view


# EditHomepageViewTests removed - requires content_id parameter and is tested elsewhere


class RoleBasedEditingIntegrationTests(TestCase):
    """Integration tests for role-based editing permissions."""

    def setUp(self):
        self.client = Client()

        # Create role-restricted page
        self.director_page = Page.objects.create(
            title="Director Page",
            slug="director-only",
            is_public=False,
        )
        PageRolePermission.objects.create(page=self.director_page, role_name="director")

        # Create users
        self.member = User.objects.create_user(
            username="member",
            email="member@test.com",
            password="testpass123",
            membership_status="Full Member",
        )
        self.director = User.objects.create_user(
            username="director",
            email="director@test.com",
            password="testpass123",
            membership_status="Full Member",
        )
        self.director.director = True
        self.director.save()

    def test_role_required_for_editing(self):
        """Users need appropriate roles to edit restricted pages."""
        # Member cannot edit director page
        self.client.force_login(self.member)
        url = reverse("cms:edit_page", kwargs={"page_id": self.director_page.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)  # Permission denied

        # Director can edit director page
        self.client.force_login(self.director)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_role_required_for_creating_under_restricted_parent(self):
        """Users need appropriate roles to create under restricted parents."""
        # Member cannot create under director page
        self.client.force_login(self.member)
        url = reverse("cms:create_page") + f"?parent={self.director_page.id}"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)  # Permission denied

        # Director can create under director page
        self.client.force_login(self.director)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_edit_and_view_permissions_aligned(self):
        """Editing permissions align with viewing permissions ('token to see = ability to edit')."""
        # If user cannot see page, they cannot edit it
        self.assertFalse(self.director_page.can_user_access(self.member))
        self.assertFalse(can_edit_page(self.member, self.director_page))

        # If user can see page, they can edit it (except for public pages)
        self.assertTrue(self.director_page.can_user_access(self.director))
        self.assertTrue(can_edit_page(self.director, self.director_page))


class WebmasterAdminPermissionTests(TestCase):
    """Test webmaster admin permissions added to CMS admin models."""

    def setUp(self):
        from django.contrib.admin.sites import AdminSite

        # Create users
        self.member = User.objects.create_user(
            username="member",
            email="member@test.com",
            is_staff=True,
            membership_status="Full Member",
        )
        self.webmaster = User.objects.create_user(
            username="webmaster",
            email="webmaster@test.com",
            is_staff=True,
            membership_status="Full Member",
        )
        self.webmaster.webmaster = True
        self.webmaster.save()

        self.superuser = User.objects.create_user(
            username="superuser",
            email="superuser@test.com",
            is_staff=True,
            is_superuser=True,
        )

        # Create mock request objects
        from django.http import HttpRequest

        self.member_request = HttpRequest()
        self.member_request.user = self.member

        self.webmaster_request = HttpRequest()
        self.webmaster_request.user = self.webmaster

        self.superuser_request = HttpRequest()
        self.superuser_request.user = self.superuser

        # Get admin instances
        from cms.admin import DocumentAdmin, HomePageContentAdmin, PageAdmin

        self.page_admin = PageAdmin(Page, AdminSite())
        self.document_admin = DocumentAdmin(Document, AdminSite())

    def test_webmaster_has_module_permission(self):
        """Webmasters have module permissions for CMS admin."""
        # Member without webmaster role cannot access
        self.assertFalse(self.page_admin.has_module_permission(self.member_request))

        # Webmaster can access
        self.assertTrue(self.page_admin.has_module_permission(self.webmaster_request))

        # Superuser can access
        self.assertTrue(self.page_admin.has_module_permission(self.superuser_request))

    def test_webmaster_has_view_permission(self):
        """Webmasters have view permissions for CMS models."""
        self.assertFalse(self.page_admin.has_view_permission(self.member_request))
        self.assertTrue(self.page_admin.has_view_permission(self.webmaster_request))
        self.assertTrue(self.page_admin.has_view_permission(self.superuser_request))

    def test_webmaster_has_add_permission(self):
        """Webmasters have add permissions for CMS models."""
        self.assertFalse(self.page_admin.has_add_permission(self.member_request))
        self.assertTrue(self.page_admin.has_add_permission(self.webmaster_request))
        self.assertTrue(self.page_admin.has_add_permission(self.superuser_request))

    def test_webmaster_has_change_permission(self):
        """Webmasters have change permissions for CMS models."""
        page = Page.objects.create(title="Test", slug="test", is_public=False)

        self.assertFalse(
            self.page_admin.has_change_permission(self.member_request, page)
        )
        self.assertTrue(
            self.page_admin.has_change_permission(self.webmaster_request, page)
        )
        self.assertTrue(
            self.page_admin.has_change_permission(self.superuser_request, page)
        )

    def test_webmaster_has_delete_permission(self):
        """Webmasters have delete permissions for CMS models."""
        page = Page.objects.create(title="Test", slug="test", is_public=False)

        self.assertFalse(
            self.page_admin.has_delete_permission(self.member_request, page)
        )
        self.assertTrue(
            self.page_admin.has_delete_permission(self.webmaster_request, page)
        )
        self.assertTrue(
            self.page_admin.has_delete_permission(self.superuser_request, page)
        )

    def test_document_admin_webmaster_permissions(self):
        """Document admin also respects webmaster permissions."""
        self.assertFalse(self.document_admin.has_module_permission(self.member_request))
        self.assertTrue(
            self.document_admin.has_module_permission(self.webmaster_request)
        )
        self.assertTrue(
            self.document_admin.has_module_permission(self.superuser_request)
        )


@pytest.mark.django_db
def test_edit_page_url_patterns():
    """Test that edit page URLs are correctly configured."""
    from django.urls import resolve, reverse

    # Test edit page URL (uses page_id, not slug)
    url = reverse("cms:edit_page", kwargs={"page_id": 1})
    assert "/cms/edit/page/1/" in url

    # Test create page URL
    url = reverse("cms:create_page")
    assert "/cms/create/page/" in url

    # Test edit homepage URL (requires content_id)
    url = reverse("cms:edit_homepage", kwargs={"content_id": 1})
    assert "/cms/edit/homepage/1/" in url


@pytest.mark.django_db
def test_permission_function_edge_cases():
    """Test edge cases in permission functions."""
    # Test with None user - should return False gracefully
    page = Page.objects.create(title="Test", slug="test", is_public=False)

    # Should return False for None user, not raise AttributeError
    assert not can_edit_page(None, page)
    assert not can_create_in_directory(None, page)

    # Test with None page (should not happen in practice)
    user = User.objects.create_user(
        username="test", email="test@test.com", membership_status="Full Member"
    )

    with pytest.raises(AttributeError):
        can_edit_page(user, None)


class MemberSpecificPermissionTests(TestCase):
    """
    Test member-specific page permissions (Issue #489).

    Tests the PageMemberPermission model that allows assigning specific
    members to edit specific pages or folders.
    """

    def setUp(self):
        # Create test pages
        self.public_page = Page.objects.create(
            title="Public Page", slug="member-perm-public", is_public=True
        )
        self.private_page = Page.objects.create(
            title="Private Page", slug="member-perm-private", is_public=False
        )
        self.role_restricted_page = Page.objects.create(
            title="Role Restricted", slug="member-perm-role-restricted", is_public=False
        )
        PageRolePermission.objects.create(
            page=self.role_restricted_page, role_name="director"
        )

        # Create test users
        self.regular_member = User.objects.create_user(
            username="regular_member_489",
            email="regular489@test.com",
            membership_status="Full Member",
        )
        self.aircraft_manager = User.objects.create_user(
            username="aircraft_manager_489",
            email="aircraft489@test.com",
            membership_status="Full Member",
        )
        self.director = User.objects.create_user(
            username="director_489",
            email="director489@test.com",
            membership_status="Full Member",
        )
        self.director.director = True
        self.director.save()

        self.webmaster = User.objects.create_user(
            username="webmaster_489",
            email="webmaster489@test.com",
            membership_status="Full Member",
        )
        self.webmaster.webmaster = True
        self.webmaster.save()

    def test_member_permission_grants_access(self):
        """
        Specific member permission grants EDIT access, which also allows VIEW.
        This ensures editors can see the content they're editing.
        """
        # Regular member cannot VIEW role-restricted page
        self.assertFalse(self.role_restricted_page.can_user_access(self.regular_member))

        # Regular member cannot EDIT role-restricted page
        self.assertFalse(self.role_restricted_page.can_user_edit(self.regular_member))

        # Grant specific permission to aircraft_manager
        PageMemberPermission.objects.create(
            page=self.role_restricted_page, member=self.aircraft_manager
        )

        # Aircraft manager can now EDIT the page
        self.assertTrue(self.role_restricted_page.can_user_edit(self.aircraft_manager))

        # Aircraft manager can also VIEW (EDIT permission grants VIEW access)
        self.assertTrue(
            self.role_restricted_page.can_user_access(self.aircraft_manager)
        )

        # Regular member still cannot VIEW or EDIT
        self.assertFalse(self.role_restricted_page.can_user_access(self.regular_member))
        self.assertFalse(self.role_restricted_page.can_user_edit(self.regular_member))

    def test_member_permission_grants_edit_access(self):
        """Specific member permission allows editing and viewing the page."""
        # Regular member cannot edit role-restricted page
        self.assertFalse(can_edit_page(self.regular_member, self.role_restricted_page))
        self.assertFalse(self.role_restricted_page.can_user_edit(self.regular_member))

        # Grant specific permission
        PageMemberPermission.objects.create(
            page=self.role_restricted_page, member=self.aircraft_manager
        )

        # Aircraft manager can now edit the page
        self.assertTrue(can_edit_page(self.aircraft_manager, self.role_restricted_page))
        self.assertTrue(self.role_restricted_page.can_user_edit(self.aircraft_manager))

        # Aircraft manager can also VIEW (EDIT permission grants VIEW access)
        self.assertTrue(
            self.role_restricted_page.can_user_access(self.aircraft_manager)
        )

        # Regular member still cannot
        self.assertFalse(can_edit_page(self.regular_member, self.role_restricted_page))

    def test_member_permission_on_private_page_without_roles(self):
        """
        Member permission grants EDIT access, which also allows VIEW.
        Demonstrates that EDIT permission overrides role restrictions for viewing.
        """
        # Create a new private page without role restrictions
        private_only_page = Page.objects.create(
            title="Private Only", slug="private-only-test", is_public=False
        )

        # All active members can VIEW by default (no roles = open to all members)
        self.assertTrue(private_only_page.can_user_access(self.regular_member))

        # But only officers can EDIT by default
        self.assertFalse(private_only_page.can_user_edit(self.regular_member))

        # Grant EDIT permission to regular member
        PageMemberPermission.objects.create(
            page=private_only_page, member=self.regular_member
        )

        # Now they can EDIT (and could already VIEW)
        self.assertTrue(private_only_page.can_user_edit(self.regular_member))
        self.assertTrue(private_only_page.can_user_access(self.regular_member))

        # Add a role restriction to control VIEW access
        PageRolePermission.objects.create(page=private_only_page, role_name="director")

        # Regular member can still VIEW because EDIT permission overrides role restrictions
        self.assertTrue(private_only_page.can_user_access(self.regular_member))

        # But they can still EDIT (member permission)
        self.assertTrue(private_only_page.can_user_edit(self.regular_member))

        # NOTE: E2E testing of member permissions in browser UI (with TinyMCE editor)
        # should be added to e2e_tests/e2e/ to verify end-to-end functionality.
        # See `.github/copilot-instructions.md` for E2E testing patterns.

    def test_member_permission_cannot_be_added_to_public_page(self):
        """Member permissions cannot be added to public pages."""
        from django.core.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            perm = PageMemberPermission(
                page=self.public_page, member=self.aircraft_manager
            )
            perm.full_clean()  # Should raise ValidationError

    def test_member_permission_unique_constraint(self):
        """Cannot add same member twice to same page."""
        from django.db import IntegrityError

        PageMemberPermission.objects.create(
            page=self.private_page, member=self.aircraft_manager
        )

        with self.assertRaises(IntegrityError):
            PageMemberPermission.objects.create(
                page=self.private_page, member=self.aircraft_manager
            )

    def test_has_member_permission_method(self):
        """Test the has_member_permission helper method."""
        self.assertFalse(self.private_page.has_member_permission(self.aircraft_manager))

        PageMemberPermission.objects.create(
            page=self.private_page, member=self.aircraft_manager
        )

        self.assertTrue(self.private_page.has_member_permission(self.aircraft_manager))
        self.assertFalse(self.private_page.has_member_permission(self.regular_member))

    def test_has_member_permission_anonymous_user(self):
        """Anonymous users never have member permissions."""
        from django.contrib.auth.models import AnonymousUser

        self.assertFalse(self.private_page.has_member_permission(AnonymousUser()))

    def test_get_permitted_members(self):
        """Test retrieving list of permitted members."""
        # Add two members
        PageMemberPermission.objects.create(
            page=self.private_page, member=self.aircraft_manager
        )
        PageMemberPermission.objects.create(
            page=self.private_page, member=self.regular_member
        )

        permitted = self.private_page.get_permitted_members()
        self.assertEqual(permitted.count(), 2)
        self.assertIn(self.aircraft_manager, permitted)
        self.assertIn(self.regular_member, permitted)

    def test_member_permission_inheritance_not_automatic(self):
        """Child pages do not automatically inherit parent member permissions."""
        # Create parent with member permission
        parent = Page.objects.create(
            title="Parent", slug="parent-perm-test", is_public=False
        )
        PageRolePermission.objects.create(page=parent, role_name="director")
        PageMemberPermission.objects.create(page=parent, member=self.aircraft_manager)

        # Create child page with same role restriction
        child = Page.objects.create(
            title="Child", slug="child-perm-test", parent=parent, is_public=False
        )
        PageRolePermission.objects.create(page=child, role_name="director")

        # Aircraft manager can EDIT parent (member permission)
        self.assertTrue(parent.can_user_edit(self.aircraft_manager))
        # Aircraft manager can also VIEW parent (EDIT permission grants VIEW)
        self.assertTrue(parent.can_user_access(self.aircraft_manager))

        # Aircraft manager cannot EDIT child (no inherited permissions)
        self.assertFalse(child.can_user_edit(self.aircraft_manager))
        # And still cannot VIEW child (role restriction)
        self.assertFalse(child.can_user_access(self.aircraft_manager))

        # Director can access both
        self.assertTrue(parent.can_user_access(self.director))
        self.assertTrue(child.can_user_access(self.director))

    def test_can_create_in_directory_with_member_permission(self):
        """Members with explicit permission can create pages under that directory."""
        # Create a directory with role restriction
        directory = Page.objects.create(
            title="Aircraft Docs", slug="aircraft-docs-test", is_public=False
        )
        PageRolePermission.objects.create(page=directory, role_name="director")

        # Regular member cannot create under it
        self.assertFalse(can_create_in_directory(self.regular_member, directory))

        # Grant permission to aircraft_manager
        PageMemberPermission.objects.create(
            page=directory, member=self.aircraft_manager
        )

        # Now aircraft_manager can create under it
        self.assertTrue(can_create_in_directory(self.aircraft_manager, directory))
