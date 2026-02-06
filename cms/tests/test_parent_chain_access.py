"""
Tests for parent chain access control.

Verifies that restricted parent pages block access to child pages.
"""

from django.test import TestCase

from cms.models import Page, PageRolePermission
from members.models import Member


class ParentChainAccessControlTests(TestCase):
    """Test that access control checks the entire parent chain."""

    def setUp(self):
        """Set up test data."""
        # Create regular member
        self.member = Member.objects.create_user(
            username="member",
            email="member@test.com",
            first_name="Test",
            last_name="Member",
            membership_status="Full Member",
        )

        # Create director with director=True attribute
        self.director = Member.objects.create_user(
            username="director",
            email="director@test.com",
            first_name="Test",
            last_name="Director",
            membership_status="Full Member",
            director=True,
        )

        # Private parent (directors only)
        self.private_parent = Page.objects.create(
            title="Private Parent",
            slug="private-parent",
            content="Private content",
            is_public=False,
        )
        PageRolePermission.objects.create(
            page=self.private_parent, role_name="director"
        )

        # Private child under private parent
        self.private_child = Page.objects.create(
            title="Private Child",
            slug="private-child",
            content="Private child content",
            parent=self.private_parent,
            is_public=False,
        )
        PageRolePermission.objects.create(page=self.private_child, role_name="director")

        # Public page for comparison
        self.public_page = Page.objects.create(
            title="Public Page",
            slug="public-page",
            content="Public content",
            is_public=True,
        )

    def test_anonymous_blocked_by_parent(self):
        """Anonymous users can't access child when parent is restricted."""
        url = self.private_child.get_absolute_url()
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_member_blocked_by_parent(self):
        """Regular members can't access child when parent restricts to directors."""
        self.client.force_login(self.member)
        url = self.private_child.get_absolute_url()
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)

    def test_director_accesses_child(self):
        """Directors with parent access CAN access child."""
        self.client.force_login(self.director)
        url = self.private_child.get_absolute_url()
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Private child content")

    def test_public_page_accessible(self):
        """Public pages remain accessible."""
        url = self.public_page.get_absolute_url()
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Public content")
