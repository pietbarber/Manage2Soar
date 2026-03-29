"""E2E coverage for Issue #746 navbar information architecture updates."""

from django.core.cache import cache

from cms.models import HomePageContent
from e2e_tests.e2e.conftest import DjangoPlaywrightTestCase
from siteconfig.models import SiteConfiguration


class TestNavbarResourcesDrawer(DjangoPlaywrightTestCase):
    """Verify guest/member navbar structures and Resources drawer behavior."""

    _TEST_WEBCAM_URL = "file:///nonexistent/webcam.jpg"

    def setUp(self):
        super().setUp()
        HomePageContent.objects.get_or_create(
            slug="home",
            defaults={
                "title": "Home",
                "audience": "public",
                "content": "<p>Public home</p>",
            },
        )
        HomePageContent.objects.get_or_create(
            slug="member-home",
            defaults={
                "title": "Member Home",
                "audience": "member",
                "content": "<p>Member home</p>",
            },
        )

    def _open_mobile_menu(self):
        self.page.set_viewport_size({"width": 390, "height": 844})
        self.page.goto(f"{self.live_server_url}/")
        self.page.click(".navbar-toggler")
        self.page.wait_for_selector("#navbarOffcanvas.show")

    def test_guest_navbar_is_simplified_on_mobile(self):
        """Anonymous users should only see simplified top-level navigation."""
        self._open_mobile_menu()

        offcanvas = self.page.locator("#navbarOffcanvas")
        assert offcanvas.locator("#guestDutyrosterDropdown").count() == 1
        assert (
            offcanvas.locator("a.nav-link", has_text="Training Syllabus").count() == 1
        )
        assert offcanvas.locator("a.nav-link", has_text="Contact Us").count() == 1
        assert (
            offcanvas.locator("a.nav-link", has_text="Membership Application").count()
            == 1
        )
        assert offcanvas.locator("#resourcesDropdown").count() == 1

        assert offcanvas.locator("#membersDropdown").count() == 0
        assert offcanvas.locator("#logsheetDropdown").count() == 0
        assert offcanvas.locator("#equipmentDropdown").count() == 0
        assert offcanvas.locator("#instructorDropdown").count() == 0

        self.page.click("#resourcesDropdown")
        self.page.wait_for_selector("#resourcesDropdown + .dropdown-menu.show")
        resources_menu = self.page.locator("#resourcesDropdown + .dropdown-menu")
        assert resources_menu.locator("a", has_text="Document Root").count() == 1
        assert resources_menu.locator("a", has_text="Report Website Issue").count() == 0

    def test_authenticated_navbar_shows_full_member_navigation(self):
        """Authenticated active members should see the full navigation model."""
        self.create_test_member(username="nav_full_member")
        self.login(username="nav_full_member")
        self._open_mobile_menu()

        offcanvas = self.page.locator("#navbarOffcanvas")
        assert offcanvas.locator("#membersDropdown").count() == 1
        assert offcanvas.locator("#dutyrosterDropdown").count() == 1
        assert offcanvas.locator("#logsheetDropdown").count() == 1
        assert offcanvas.locator("#equipmentDropdown").count() == 1
        assert offcanvas.locator("#resourcesDropdown").count() == 1

        assert offcanvas.locator("a.nav-link", has_text="Contact Us").count() == 0
        assert (
            offcanvas.locator("a.nav-link", has_text="Membership Application").count()
            == 0
        )

    def test_mobile_resources_drawer_includes_clickable_webcam_entry(self):
        """Active members should see and be able to open Webcam from mobile Resources."""
        siteconfig = SiteConfiguration.objects.first()
        if siteconfig:
            siteconfig.webcam_snapshot_url = self._TEST_WEBCAM_URL
            siteconfig.save(update_fields=["webcam_snapshot_url"])
        else:
            SiteConfiguration.objects.create(
                club_name="E2E Test Club",
                domain_name="e2e.test",
                club_abbreviation="E2E",
                webcam_snapshot_url=self._TEST_WEBCAM_URL,
            )
        cache.delete("siteconfig_webcam_enabled")

        self.create_test_member(username="nav_webcam_member")
        self.login(username="nav_webcam_member")
        self._open_mobile_menu()

        self.page.click("#resourcesDropdown")
        self.page.wait_for_selector("#resourcesDropdown + .dropdown-menu.show")
        resources_menu = self.page.locator("#resourcesDropdown + .dropdown-menu")
        webcam_link = resources_menu.locator("a.dropdown-item", has_text="Webcam")
        assert webcam_link.count() == 1

        webcam_link.first.scroll_into_view_if_needed()
        webcam_link.first.click()

        self.page.wait_for_url(f"{self.live_server_url}/webcam/")
