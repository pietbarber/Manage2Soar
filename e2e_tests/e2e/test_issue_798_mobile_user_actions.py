"""E2E coverage for Issue #798 mobile user actions and public-home access."""

from cms.models import HomePageContent
from e2e_tests.e2e.conftest import DjangoPlaywrightTestCase


class TestIssue798MobileUserActions(DjangoPlaywrightTestCase):
    """Validate mobile profile actions added for Issue #798."""

    def setUp(self):
        super().setUp()
        HomePageContent.objects.get_or_create(
            slug="home",
            defaults={
                "title": "Public Home",
                "audience": "public",
                "content": "<p>Public homepage content</p>",
            },
        )
        HomePageContent.objects.get_or_create(
            slug="member-home",
            defaults={
                "title": "Member Home",
                "audience": "member",
                "content": "<p>Member homepage content</p>",
            },
        )

    def _open_mobile_menu(self):
        self.page.set_viewport_size({"width": 390, "height": 844})
        self.page.goto(f"{self.live_server_url}/")
        self.page.click(".navbar-toggler")
        self.page.wait_for_selector("#navbarOffcanvas.show")

    def test_mobile_user_section_shows_logout_and_public_home_link(self):
        self.create_test_member(username="issue798member")
        self.login(username="issue798member")

        self._open_mobile_menu()

        offcanvas = self.page.locator("#navbarOffcanvas")
        assert offcanvas.locator(".user-section").count() == 1
        assert (
            offcanvas.locator(".user-section", has_text="View Public Homepage").count()
            == 1
        )
        assert offcanvas.locator(".user-section button", has_text="Logout").count() == 1

    def test_mobile_admin_link_visible_for_admin_capable_user(self):
        self.create_test_member(username="issue798admin", is_superuser=True)
        self.login(username="issue798admin")

        self._open_mobile_menu()

        admin_link = self.page.locator(
            "#navbarOffcanvas .user-section a", has_text="Admin Interface"
        )
        assert admin_link.count() == 1
        admin_link.click()
        self.page.wait_for_url(f"{self.live_server_url}/admin/**")

    def test_public_home_link_loads_public_homepage_for_logged_in_member(self):
        self.create_test_member(username="issue798publicview")
        self.login(username="issue798publicview")

        self._open_mobile_menu()

        self.page.click(
            "#navbarOffcanvas .user-section a:has-text('View Public Homepage')"
        )
        self.page.wait_for_url(f"{self.live_server_url}/?view=public")

        body_text = self.page.locator("body").inner_text()
        assert "Public homepage content" in body_text
        assert "Member homepage content" not in body_text
