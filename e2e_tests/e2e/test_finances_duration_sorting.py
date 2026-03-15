"""
E2E tests for finances table duration sorting behavior.

Covers JavaScript-driven sorting for the Summary by Flight Duration column,
including rows with missing durations rendered as an em dash.
"""

from datetime import date, time

from logsheet.models import Airfield, Flight, Glider, Logsheet
from siteconfig.models import SiteConfiguration

from .conftest import DjangoPlaywrightTestCase


class TestFinancesDurationSortingE2E(DjangoPlaywrightTestCase):
    """Verify duration sorting uses numeric ordering and keeps missing values last."""

    def setUp(self):
        super().setUp()

        SiteConfiguration.objects.all().delete()
        SiteConfiguration.objects.create(
            club_name="Test Club",
            domain_name="test.org",
            club_abbreviation="TC",
        )

        self.duty_officer = self.create_test_member(
            username="do_duration",
            first_name="Duty",
            last_name="Officer",
        )
        self.duty_officer.duty_officer = True
        self.duty_officer.save()

        self.pilot_alpha = self.create_test_member(
            username="pilot_alpha_duration",
            first_name="Alpha",
            last_name="Pilot",
        )
        self.pilot_bravo = self.create_test_member(
            username="pilot_bravo_duration",
            first_name="Bravo",
            last_name="Pilot",
        )
        self.pilot_charlie = self.create_test_member(
            username="pilot_charlie_duration",
            first_name="Charlie",
            last_name="Pilot",
        )

        self.airfield = Airfield.objects.create(identifier="E2ED", name="E2E Duration")
        self.glider = Glider.objects.create(
            make="Schleicher",
            model="ASK-21",
            n_number="N779E2E",
            competition_number="E2E",
            seats=2,
            is_active=True,
        )

        self.logsheet = Logsheet.objects.create(
            log_date=date.today(),
            airfield=self.airfield,
            created_by=self.duty_officer,
            duty_officer=self.duty_officer,
        )

        # 2:00:00 duration
        Flight.objects.create(
            logsheet=self.logsheet,
            airfield=self.airfield,
            pilot=self.pilot_alpha,
            glider=self.glider,
            flight_type="solo",
            launch_time=time(9, 0),
            landing_time=time(11, 0),
        )

        # Missing duration rendered as em dash
        Flight.objects.create(
            logsheet=self.logsheet,
            airfield=self.airfield,
            pilot=self.pilot_bravo,
            glider=self.glider,
            flight_type="solo",
            launch_time=time(10, 0),
            landing_time=None,
        )

        # 11:00:00 duration (kept <= 12h so computed_duration is valid)
        Flight.objects.create(
            logsheet=self.logsheet,
            airfield=self.airfield,
            pilot=self.pilot_charlie,
            glider=self.glider,
            flight_type="solo",
            launch_time=time(1, 0),
            landing_time=time(12, 0),
        )

    @staticmethod
    def _duration_to_seconds(duration_text):
        value = (duration_text or "").strip()
        if not value or value == "—":
            return None
        parts = [int(part) for part in value.split(":")]
        if len(parts) == 3:
            return parts[0] * 3600 + parts[1] * 60 + parts[2]
        if len(parts) == 2:
            return parts[0] * 60 + parts[1]
        return None

    def _read_duration_cells(self):
        rows = self.page.eval_on_selector_all(
            "h4:has-text('Summary by Flight') + div table tbody tr",
            "rows => rows.map(r => r.cells[2].textContent.trim())",
        )
        return rows

    def _assert_sorted_with_missing_last(self, durations):
        parsed = [self._duration_to_seconds(value) for value in durations]
        non_missing = [value for value in parsed if value is not None]

        assert non_missing == sorted(non_missing), (
            "Expected non-missing durations sorted ascending, got " f"{durations}"
        )

        if None in parsed:
            assert parsed[-1] is None, (
                "Expected missing duration placeholder to sort last, got "
                f"{durations}"
            )

    def _assert_desc_sorted_with_missing_last(self, durations):
        parsed = [self._duration_to_seconds(value) for value in durations]
        non_missing = [value for value in parsed if value is not None]

        assert non_missing == sorted(non_missing, reverse=True), (
            "Expected non-missing durations sorted descending, got " f"{durations}"
        )

        if None in parsed:
            assert parsed[-1] is None, (
                "Expected missing duration placeholder to remain last in descending sort, got "
                f"{durations}"
            )

    def test_duration_sort_is_numeric_and_missing_is_last(self):
        self.login(username="do_duration")
        self.page.goto(
            f"{self.live_server_url}/logsheet/manage/{self.logsheet.pk}/finances/"
        )

        duration_header = self.page.locator(
            "h4:has-text('Summary by Flight') + div table th:has-text('Duration')"
        )
        assert duration_header.count() == 1

        # Click once; if initial sort direction is descending, click again.
        duration_header.click()
        self.page.wait_for_timeout(150)
        durations = self._read_duration_cells()

        parsed = [self._duration_to_seconds(value) for value in durations]
        non_missing = [value for value in parsed if value is not None]
        is_ascending = non_missing == sorted(non_missing)
        missing_last = (None not in parsed) or (parsed[-1] is None)

        if not (is_ascending and missing_last):
            duration_header.click()
            self.page.wait_for_timeout(150)
            durations = self._read_duration_cells()

        self._assert_sorted_with_missing_last(durations)

        # Toggle to descending and ensure missing values still stay last.
        duration_header.click()
        self.page.wait_for_timeout(150)
        desc_durations = self._read_duration_cells()
        self._assert_desc_sorted_with_missing_last(desc_durations)
