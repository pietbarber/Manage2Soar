"""
Tests for CMS editing permissions and views.

Tests the new role-based editing permission system added in Issue #273.
"""

import pytest
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from cms.models import Document, Page, PageRolePermission
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
        self.anonymous_user = User()  # Not authenticated
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
        """Unrestricted private pages can be edited by any active member (since they can see them)."""
        # First verify they can see the page
        self.assertTrue(self.member_page.can_user_access(self.member))
        self.assertTrue(self.member_page.can_user_access(self.director))
        # Then verify they can edit it (token to see = ability to edit)
        self.assertTrue(can_edit_page(self.member, self.member_page))
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
        """Any active member can create under unrestricted private parents (since they can see them)."""
        # First verify they can see the parent page
        self.assertTrue(self.member_page.can_user_access(self.member))
        self.assertTrue(self.member_page.can_user_access(self.director))
        # Then verify they can create under it
        self.assertTrue(can_create_in_directory(self.member, self.member_page))
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

    def test_edit_page_requires_authentication(self):
        """Edit page returns 403 for anonymous users."""
        url = reverse("cms:edit_page", kwargs={"page_id": self.page.id})
        response = self.client.get(url)
        # View returns 403 for anonymous users
        self.assertEqual(response.status_code, 403)

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
        """Edit page allows access to users with permission."""
        self.client.force_login(self.member)
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
        """POST to edit page updates the page content."""
        self.client.force_login(self.member)
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
        self.client.force_login(self.member)
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

    def test_create_page_requires_authentication(self):
        """Create page returns 403 for anonymous users."""
        url = reverse("cms:create_page")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)  # View returns 403, not redirect

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
        """POST to create page creates a new page."""
        self.client.force_login(self.member)
        url = reverse("cms:create_page") + f"?parent={self.parent_page.id}"

        form_data = {
            "title": "New Page",
            "slug": "new-page",
            "parent": self.parent_page.id,  # Include parent in form data
            "content": "<p>New content</p>",
            "is_public": False,
            "documents-TOTAL_FORMS": "0",
            "documents-INITIAL_FORMS": "0",
            "documents-MIN_NUM_FORMS": "0",
            "documents-MAX_NUM_FORMS": "1000",
        }

        # Member can create under unrestricted private parent page (following 'token to see = ability to edit' logic)
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
    # Test with None user
    page = Page.objects.create(title="Test", slug="test", is_public=False)

    with pytest.raises(AttributeError):
        can_edit_page(None, page)

    with pytest.raises(AttributeError):
        can_create_in_directory(None, page)

    # Test with None page (should not happen in practice)
    user = User.objects.create_user(
        username="test", email="test@test.com", membership_status="Full Member"
    )

    with pytest.raises(AttributeError):
        can_edit_page(user, None)
