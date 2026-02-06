"""
Tests for CMS subpage creation feature (Issue #596).

Tests the "Create Subpage" button, parent pre-population, permission copying,
disabled parent field, and URL depth support up to 10 levels.
"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from cms.models import Page, PageMemberPermission, PageRolePermission

User = get_user_model()


class SubpageButtonVisibilityTests(TestCase):
    """Test that the 'Create Subpage' button appears for authorized users."""

    def setUp(self):
        self.client = Client()

        self.page = Page.objects.create(
            title="Parent Page", slug="parent-page", is_public=False
        )

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

    def test_create_subpage_button_visible_for_webmaster(self):
        """Webmaster should see the 'Create Subpage' button."""
        self.client.force_login(self.webmaster)
        response = self.client.get(f"/cms/{self.page.slug}/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Create Subpage")
        self.assertContains(response, f"?parent={self.page.id}")

    def test_create_subpage_button_visible_for_director(self):
        """Director (officer) should see the 'Create Subpage' button."""
        self.client.force_login(self.director)
        response = self.client.get(f"/cms/{self.page.slug}/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Create Subpage")

    def test_create_subpage_button_hidden_for_regular_member(self):
        """Regular members without edit permission should NOT see the button."""
        self.client.force_login(self.member)
        response = self.client.get(f"/cms/{self.page.slug}/")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Create Subpage")

    def test_create_subpage_button_hidden_for_anonymous(self):
        """Anonymous users should not see the button (public page test)."""
        self.page.is_public = True
        self.page.save()
        response = self.client.get(f"/cms/{self.page.slug}/")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Create Subpage")

    def test_create_subpage_button_visible_for_member_with_edit_permission(self):
        """Members with explicit PageMemberPermission should see the button."""
        PageMemberPermission.objects.create(page=self.page, member=self.member)
        self.client.force_login(self.member)
        response = self.client.get(f"/cms/{self.page.slug}/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Create Subpage")

    def test_context_has_can_create_subpage(self):
        """The context should include can_create_subpage flag."""
        self.client.force_login(self.webmaster)
        response = self.client.get(f"/cms/{self.page.slug}/")
        self.assertIn("can_create_subpage", response.context)
        self.assertTrue(response.context["can_create_subpage"])

    def test_context_can_create_subpage_false_for_member(self):
        """Regular member should have can_create_subpage=False."""
        self.client.force_login(self.member)
        response = self.client.get(f"/cms/{self.page.slug}/")
        self.assertIn("can_create_subpage", response.context)
        self.assertFalse(response.context["can_create_subpage"])


class SubpageFormPrePopulationTests(TestCase):
    """Test that create page form is pre-populated when creating subpages."""

    def setUp(self):
        self.client = Client()

        self.parent_page = Page.objects.create(
            title="Parent Page", slug="parent-page", is_public=False
        )
        # Add role restrictions to parent
        PageRolePermission.objects.create(page=self.parent_page, role_name="director")
        PageRolePermission.objects.create(page=self.parent_page, role_name="instructor")

        self.webmaster = User.objects.create_user(
            username="webmaster",
            email="webmaster@test.com",
            password="testpass123",
            membership_status="Full Member",
        )
        self.webmaster.webmaster = True
        self.webmaster.save()

    def test_parent_field_pre_populated(self):
        """Parent field should be pre-set when ?parent= is provided."""
        self.client.force_login(self.webmaster)
        url = reverse("cms:create_page") + f"?parent={self.parent_page.id}"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertEqual(form.initial.get("parent"), self.parent_page.id)

    def test_parent_field_disabled(self):
        """Parent field should be disabled when creating a subpage."""
        self.client.force_login(self.webmaster)
        url = reverse("cms:create_page") + f"?parent={self.parent_page.id}"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertTrue(form.fields["parent"].disabled)

    def test_parent_field_not_disabled_for_root_pages(self):
        """Parent field should NOT be disabled when creating root pages."""
        self.client.force_login(self.webmaster)
        url = reverse("cms:create_page")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertFalse(form.fields["parent"].disabled)

    def test_is_public_inherited_from_parent(self):
        """is_public should be inherited from parent page."""
        self.client.force_login(self.webmaster)
        url = reverse("cms:create_page") + f"?parent={self.parent_page.id}"
        response = self.client.get(url)
        form = response.context["form"]
        self.assertEqual(form.initial.get("is_public"), self.parent_page.is_public)

    def test_page_title_shows_parent_name(self):
        """Page title should include parent page name for subpages."""
        self.client.force_login(self.webmaster)
        url = reverse("cms:create_page") + f"?parent={self.parent_page.id}"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"Create Subpage under")
        self.assertContains(response, self.parent_page.title)

    def test_is_subpage_context(self):
        """Context should include is_subpage and parent_page."""
        self.client.force_login(self.webmaster)
        url = reverse("cms:create_page") + f"?parent={self.parent_page.id}"
        response = self.client.get(url)
        self.assertTrue(response.context["is_subpage"])
        self.assertEqual(response.context["parent_page"], self.parent_page)

    def test_not_subpage_context_for_root(self):
        """Context should not mark as subpage when no parent."""
        self.client.force_login(self.webmaster)
        url = reverse("cms:create_page")
        response = self.client.get(url)
        self.assertFalse(response.context.get("is_subpage", False))
        self.assertIsNone(response.context.get("parent_page"))

    def test_disabled_parent_info_message(self):
        """Template should show info message about disabled parent field."""
        self.client.force_login(self.webmaster)
        url = reverse("cms:create_page") + f"?parent={self.parent_page.id}"
        response = self.client.get(url)
        self.assertContains(response, "Parent page is pre-set for this subpage")


class SubpagePermissionCopyingTests(TestCase):
    """Test that permissions are copied from parent when creating subpages."""

    def setUp(self):
        self.client = Client()

        # Create parent page with permissions
        self.parent_page = Page.objects.create(
            title="Parent Page", slug="parent-page", is_public=False
        )
        # Add role permissions to parent
        PageRolePermission.objects.create(page=self.parent_page, role_name="director")
        PageRolePermission.objects.create(page=self.parent_page, role_name="instructor")

        # Create a member with edit permission on parent
        self.editor = User.objects.create_user(
            username="editor",
            email="editor@test.com",
            password="testpass123",
            membership_status="Full Member",
        )
        PageMemberPermission.objects.create(page=self.parent_page, member=self.editor)

        # Create webmaster
        self.webmaster = User.objects.create_user(
            username="webmaster",
            email="webmaster@test.com",
            password="testpass123",
            membership_status="Full Member",
        )
        self.webmaster.webmaster = True
        self.webmaster.save()

    def test_role_permissions_copied_to_subpage(self):
        """Role permissions should be copied from parent to new subpage."""
        self.client.force_login(self.webmaster)
        url = reverse("cms:create_page") + f"?parent={self.parent_page.id}"
        form_data = {
            "title": "New Subpage",
            "slug": "new-subpage",
            "parent": self.parent_page.id,
            "content": "<p>Subpage content</p>",
            "is_public": False,
            "documents-TOTAL_FORMS": "0",
            "documents-INITIAL_FORMS": "0",
            "documents-MIN_NUM_FORMS": "0",
            "documents-MAX_NUM_FORMS": "1000",
        }
        response = self.client.post(url, data=form_data)
        self.assertEqual(response.status_code, 302)

        new_page = Page.objects.get(slug="new-subpage")
        # Check role permissions were copied
        new_roles = set(new_page.role_permissions.values_list("role_name", flat=True))
        parent_roles = set(
            self.parent_page.role_permissions.values_list("role_name", flat=True)
        )
        self.assertEqual(new_roles, parent_roles)
        self.assertIn("director", new_roles)
        self.assertIn("instructor", new_roles)

    def test_member_permissions_copied_to_subpage(self):
        """Member edit permissions should be copied from parent to new subpage."""
        self.client.force_login(self.webmaster)
        url = reverse("cms:create_page") + f"?parent={self.parent_page.id}"
        form_data = {
            "title": "New Subpage Member",
            "slug": "new-subpage-member",
            "parent": self.parent_page.id,
            "content": "<p>Content</p>",
            "is_public": False,
            "documents-TOTAL_FORMS": "0",
            "documents-INITIAL_FORMS": "0",
            "documents-MIN_NUM_FORMS": "0",
            "documents-MAX_NUM_FORMS": "1000",
        }
        response = self.client.post(url, data=form_data)
        self.assertEqual(response.status_code, 302)

        new_page = Page.objects.get(slug="new-subpage-member")
        # Check member permissions were copied
        new_members = set(
            new_page.member_permissions.values_list("member_id", flat=True)
        )
        self.assertIn(self.editor.id, new_members)

    def test_no_permissions_copied_for_root_page(self):
        """Root-level pages should not have permissions copied."""
        self.client.force_login(self.webmaster)
        url = reverse("cms:create_page")
        form_data = {
            "title": "Root Page",
            "slug": "root-page",
            "content": "<p>Root content</p>",
            "is_public": True,
            "documents-TOTAL_FORMS": "0",
            "documents-INITIAL_FORMS": "0",
            "documents-MIN_NUM_FORMS": "0",
            "documents-MAX_NUM_FORMS": "1000",
        }
        response = self.client.post(url, data=form_data)
        self.assertEqual(response.status_code, 302)

        new_page = Page.objects.get(slug="root-page")
        self.assertEqual(new_page.role_permissions.count(), 0)
        self.assertEqual(new_page.member_permissions.count(), 0)

    def test_subpage_parent_set_correctly(self):
        """Subpage should have the correct parent page set."""
        self.client.force_login(self.webmaster)
        url = reverse("cms:create_page") + f"?parent={self.parent_page.id}"
        form_data = {
            "title": "Child Page",
            "slug": "child-page",
            "parent": self.parent_page.id,
            "content": "<p>Child content</p>",
            "is_public": False,
            "documents-TOTAL_FORMS": "0",
            "documents-INITIAL_FORMS": "0",
            "documents-MIN_NUM_FORMS": "0",
            "documents-MAX_NUM_FORMS": "1000",
        }
        response = self.client.post(url, data=form_data)
        self.assertEqual(response.status_code, 302)

        new_page = Page.objects.get(slug="child-page")
        self.assertEqual(new_page.parent, self.parent_page)

    def test_duplicate_permissions_not_created(self):
        """Creating a subpage should not create duplicate permissions via get_or_create."""
        self.client.force_login(self.webmaster)
        url = reverse("cms:create_page") + f"?parent={self.parent_page.id}"
        form_data = {
            "title": "Test Duplicate",
            "slug": "test-duplicate",
            "parent": self.parent_page.id,
            "content": "",
            "is_public": False,
            "documents-TOTAL_FORMS": "0",
            "documents-INITIAL_FORMS": "0",
            "documents-MIN_NUM_FORMS": "0",
            "documents-MAX_NUM_FORMS": "1000",
        }
        response = self.client.post(url, data=form_data)
        self.assertEqual(response.status_code, 302)

        new_page = Page.objects.get(slug="test-duplicate")
        # Should have exactly the same count as parent (no duplicates)
        self.assertEqual(
            new_page.role_permissions.count(),
            self.parent_page.role_permissions.count(),
        )
        self.assertEqual(
            new_page.member_permissions.count(),
            self.parent_page.member_permissions.count(),
        )


class URLDepthTests(TestCase):
    """Test that URL routing supports up to 10 levels of nesting."""

    def setUp(self):
        self.client = Client()

        self.webmaster = User.objects.create_user(
            username="webmaster",
            email="webmaster@test.com",
            password="testpass123",
            membership_status="Full Member",
        )
        self.webmaster.webmaster = True
        self.webmaster.save()

    def _create_nested_pages(self, depth):
        """Create a chain of nested pages up to the given depth."""
        pages = []
        parent = None
        for i in range(depth):
            page = Page.objects.create(
                title=f"Level {i + 1}",
                slug=f"level-{i + 1}",
                parent=parent,
                is_public=True,
            )
            pages.append(page)
            parent = page
        return pages

    def test_single_level_url(self):
        """Single-level page URL should work."""
        pages = self._create_nested_pages(1)
        response = self.client.get("/cms/level-1/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page"], pages[0])

    def test_three_level_url(self):
        """Three-level nested URL should work (original limit)."""
        pages = self._create_nested_pages(3)
        response = self.client.get("/cms/level-1/level-2/level-3/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page"], pages[2])

    def test_five_level_url(self):
        """Five-level nested URL should work (beyond old limit)."""
        pages = self._create_nested_pages(5)
        response = self.client.get("/cms/level-1/level-2/level-3/level-4/level-5/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page"], pages[4])

    def test_ten_level_url(self):
        """Ten-level nested URL should work (new maximum)."""
        pages = self._create_nested_pages(10)
        path = "/cms/" + "/".join(f"level-{i + 1}" for i in range(10)) + "/"
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page"], pages[9])

    def test_breadcrumbs_for_deep_nesting(self):
        """Breadcrumbs should be built correctly for deeply nested pages."""
        self._create_nested_pages(5)
        self.client.force_login(self.webmaster)
        path = "/cms/" + "/".join(f"level-{i + 1}" for i in range(5)) + "/"
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        breadcrumbs = response.context["breadcrumbs"]
        # Should have Resources + 4 parent entries (not including current page)
        self.assertEqual(len(breadcrumbs), 5)
        self.assertEqual(breadcrumbs[0]["title"], "Resources")
        for i in range(1, 5):
            self.assertEqual(breadcrumbs[i]["title"], f"Level {i}")

    def test_get_absolute_url_deep_nesting(self):
        """Page.get_absolute_url() should return correct path for deep nesting."""
        pages = self._create_nested_pages(5)
        expected = "/cms/level-1/level-2/level-3/level-4/level-5/"
        self.assertEqual(pages[4].get_absolute_url(), expected)

    def test_nonexistent_slug_404(self):
        """Nonexistent slug in a valid path should return 404."""
        self._create_nested_pages(2)
        response = self.client.get("/cms/level-1/nonexistent/")
        self.assertEqual(response.status_code, 404)

    def test_mismatched_hierarchy_404(self):
        """Accessing a child under wrong parent should return 404."""
        self._create_nested_pages(3)
        # level-3 is child of level-2, not level-1
        response = self.client.get("/cms/level-1/level-3/")
        self.assertEqual(response.status_code, 404)


class SubpageCreationByEditorTests(TestCase):
    """Test that members with PageMemberPermission can create subpages."""

    def setUp(self):
        self.client = Client()

        self.parent_page = Page.objects.create(
            title="Editor Parent",
            slug="editor-parent",
            is_public=False,
        )

        self.editor = User.objects.create_user(
            username="editor",
            email="editor@test.com",
            password="testpass123",
            membership_status="Full Member",
        )
        # Give editor explicit edit permission on parent
        PageMemberPermission.objects.create(page=self.parent_page, member=self.editor)

        self.regular_member = User.objects.create_user(
            username="regular",
            email="regular@test.com",
            password="testpass123",
            membership_status="Full Member",
        )

    def test_editor_can_access_create_subpage_form(self):
        """Editor with PageMemberPermission can access create subpage form."""
        self.client.force_login(self.editor)
        url = reverse("cms:create_page") + f"?parent={self.parent_page.id}"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_editor_can_create_subpage(self):
        """Editor with PageMemberPermission can POST to create a subpage."""
        self.client.force_login(self.editor)
        url = reverse("cms:create_page") + f"?parent={self.parent_page.id}"
        form_data = {
            "title": "Editor Subpage",
            "slug": "editor-subpage",
            "parent": self.parent_page.id,
            "content": "<p>Editor content</p>",
            "is_public": False,
            "documents-TOTAL_FORMS": "0",
            "documents-INITIAL_FORMS": "0",
            "documents-MIN_NUM_FORMS": "0",
            "documents-MAX_NUM_FORMS": "1000",
        }
        response = self.client.post(url, data=form_data)
        self.assertEqual(response.status_code, 302)
        new_page = Page.objects.get(slug="editor-subpage")
        self.assertEqual(new_page.parent, self.parent_page)

    def test_regular_member_cannot_create_subpage(self):
        """Regular members without edit permission are forbidden."""
        self.client.force_login(self.regular_member)
        url = reverse("cms:create_page") + f"?parent={self.parent_page.id}"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_editor_permissions_inherited_by_subpage(self):
        """Editor's permission on parent should be copied to the new subpage."""
        self.client.force_login(self.editor)
        url = reverse("cms:create_page") + f"?parent={self.parent_page.id}"
        form_data = {
            "title": "Inherited Perms",
            "slug": "inherited-perms",
            "parent": self.parent_page.id,
            "content": "",
            "is_public": False,
            "documents-TOTAL_FORMS": "0",
            "documents-INITIAL_FORMS": "0",
            "documents-MIN_NUM_FORMS": "0",
            "documents-MAX_NUM_FORMS": "1000",
        }
        response = self.client.post(url, data=form_data)
        self.assertEqual(response.status_code, 302)

        new_page = Page.objects.get(slug="inherited-perms")
        # Editor should have permission on the new page too
        self.assertTrue(new_page.member_permissions.filter(member=self.editor).exists())
