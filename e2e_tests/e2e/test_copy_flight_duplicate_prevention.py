"""
E2E regression tests for duplicate prevention when copying flights.

Covers the user-reported behavior where operators rapidly click through the
Copy -> Add Flight flow on slow connections.
"""

from datetime import date, time

from e2e_tests.e2e.conftest import DjangoPlaywrightTestCase
from logsheet.models import Airfield, Flight, Glider, Logsheet
from siteconfig.models import SiteConfiguration


class TestCopyFlightDuplicatePrevention(DjangoPlaywrightTestCase):
    """Verify copy-flight UX guards prevent accidental duplicate flight rows."""

    def setUp(self):
        super().setUp()
        self.member = self.create_test_member(username="copytester", is_superuser=True)
        self.login(username="copytester")

        self.airfield = Airfield.objects.create(
            identifier="KCPY",
            name="Copy Test Airfield",
            is_active=True,
        )
        self.glider = Glider.objects.create(
            make="Schleicher",
            model="ASK-21",
            n_number="NCPY1",
            competition_number="CPY",
            seats=2,
            is_active=True,
        )
        self.logsheet = Logsheet.objects.create(
            log_date=date(2026, 1, 25),
            airfield=self.airfield,
            created_by=self.member,
            duty_officer=self.member,
        )

        self.seed_flight = Flight.objects.create(
            logsheet=self.logsheet,
            pilot=self.member,
            glider=self.glider,
            airfield=self.airfield,
            launch_time=time(9, 0),
            landing_time=time(9, 20),
            release_altitude=3000,
            flight_type="solo",
        )

        if not SiteConfiguration.objects.first():
            SiteConfiguration.objects.create(
                club_name="Test Club",
                domain_name="test.example.com",
                club_abbreviation="TC",
                quick_altitude_buttons="2000,3000",
            )

    def _open_copy_modal_for_seed_flight(self):
        self.page.goto(f"{self.live_server_url}/logsheet/manage/{self.logsheet.pk}/")
        self.page.click(f'.copy-flight-btn[data-flight-id="{self.seed_flight.pk}"]')
        self.page.wait_for_selector("#flightModal", state="visible")
        self.page.wait_for_selector("#edit-flight-form")

    def _submit_copy_form(self, *, rapid_double_click=False):
        submit_button = self.page.locator(
            '#edit-flight-form button[type="submit"]'
        ).first
        if rapid_double_click:
            with self.page.expect_navigation(wait_until="networkidle"):
                submit_button.dblclick()
            return

        with self.page.expect_navigation(wait_until="networkidle"):
            submit_button.click()

    def test_copy_modal_rapid_double_submit_creates_only_one_new_flight(self):
        """Double-clicking Add Flight should not create duplicate rows."""
        self._open_copy_modal_for_seed_flight()
        self._submit_copy_form(rapid_double_click=True)

        assert Flight.objects.filter(logsheet=self.logsheet).count() == 2

    def test_copy_modal_intentional_repeat_creates_two_distinct_new_flights(self):
        """Submitting two separate copy actions should still create two flights."""
        self._open_copy_modal_for_seed_flight()
        self._submit_copy_form()
        assert Flight.objects.filter(logsheet=self.logsheet).count() == 2

        self._open_copy_modal_for_seed_flight()
        self._submit_copy_form()
        assert Flight.objects.filter(logsheet=self.logsheet).count() == 3
