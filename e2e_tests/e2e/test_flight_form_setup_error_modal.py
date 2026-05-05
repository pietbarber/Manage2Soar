"""
E2E tests for flight form setup error display in the AJAX modal (PR #900).

Verifies that when the server returns a 500 JSON error (e.g., missing
SiteConfiguration), the Add Flight / Edit Flight modal displays the
server-provided ``payload.error`` message rather than the generic fallback.

This guards against regressions in the JS fetch handler in logsheet_manage.html
that parses structured JSON error payloads and injects them into the modal body.
"""

from datetime import date

from e2e_tests.e2e.conftest import DjangoPlaywrightTestCase
from logsheet.models import Airfield, Flight, Glider, Logsheet
from siteconfig.models import SiteConfiguration


class TestFlightFormSetupErrorModal(DjangoPlaywrightTestCase):
    """Modal correctly surfaces server-provided JSON error messages."""

    def setUp(self):
        super().setUp()
        self.member = self.create_test_member(username="pilottest", is_superuser=True)
        self.login(username="pilottest")

        self.airfield = Airfield.objects.create(
            identifier="KFRR", name="Front Royal Airport", is_active=True
        )
        self.glider = Glider.objects.create(
            make="Schleicher",
            model="ASK-21",
            n_number="N900PR",
            competition_number="P1",
            seats=2,
            is_active=True,
        )
        self.logsheet = Logsheet.objects.create(
            log_date=date(2026, 1, 20),
            airfield=self.airfield,
            created_by=self.member,
            duty_officer=self.member,
        )

    # ------------------------------------------------------------------
    # Add Flight: missing SiteConfiguration → modal shows server message
    # ------------------------------------------------------------------

    def test_add_flight_modal_shows_server_error_when_site_config_missing(self):
        """
        When SiteConfiguration is absent, clicking Add Flight should open the
        modal and display the server-provided error text (not the generic JS
        fallback) so admins know exactly what to fix.
        """
        # Ensure no SiteConfiguration exists (PR #900 regression scenario)
        SiteConfiguration.objects.all().delete()

        self.page.goto(f"{self.live_server_url}/logsheet/manage/{self.logsheet.pk}/")

        # Click the Add Flight button to trigger the AJAX modal fetch
        add_btn = self.page.locator(
            f"a[data-url*='add-flight'][data-bs-target='#flightModal']"
        ).first
        add_btn.click()

        # Wait for the modal to be visible
        modal = self.page.locator("#flightModal")
        modal.wait_for(state="visible", timeout=5000)

        # Wait for the fetch to complete (loading spinner → error content)
        self.page.wait_for_function(
            "() => !document.querySelector('#flightModalContent .spinner-border')",
            timeout=8000,
        )

        modal_body = self.page.locator("#flightModalContent").inner_text()

        # The server returns: "Flight form setup is incomplete: Site Configuration
        # is missing. An admin should create it in Admin > Siteconfig > Site
        # Configuration." — verify the key phrase is visible in the modal.
        assert (
            "Site Configuration is missing" in modal_body
        ), f"Expected server-provided error message in modal, got: {modal_body!r}"

        # Confirm the generic JS fallback message is NOT shown
        assert (
            "The server could not load the flight form" not in modal_body
        ), "Generic JS fallback message shown instead of server-provided error"

    # ------------------------------------------------------------------
    # Edit Flight: missing SiteConfiguration → modal shows server message
    # ------------------------------------------------------------------

    def test_edit_flight_modal_shows_server_error_when_site_config_missing(self):
        """
        Same scenario for an existing flight's Edit button.
        """
        # Need a SiteConfiguration to create the flight row, then delete it
        SiteConfiguration.objects.create(
            club_name="Test Club",
            domain_name="test.example.com",
            club_abbreviation="TC",
        )
        flight = Flight.objects.create(
            logsheet=self.logsheet,
            pilot=self.member,
            glider=self.glider,
            airfield=self.airfield,
            flight_type="solo",
        )
        # Now remove the SiteConfiguration to trigger the error
        SiteConfiguration.objects.all().delete()

        self.page.goto(f"{self.live_server_url}/logsheet/manage/{self.logsheet.pk}/")

        # Locate the Edit button for this specific flight
        edit_btn = self.page.locator(
            f"a[data-url*='edit-flight/{flight.pk}'][data-bs-target='#flightModal']"
        ).first
        edit_btn.click()

        modal = self.page.locator("#flightModal")
        modal.wait_for(state="visible", timeout=5000)

        self.page.wait_for_function(
            "() => !document.querySelector('#flightModalContent .spinner-border')",
            timeout=8000,
        )

        modal_body = self.page.locator("#flightModalContent").inner_text()

        assert (
            "Site Configuration is missing" in modal_body
        ), f"Expected server-provided error message in modal, got: {modal_body!r}"
        assert (
            "The server could not load the flight form" not in modal_body
        ), "Generic JS fallback message shown instead of server-provided error"
