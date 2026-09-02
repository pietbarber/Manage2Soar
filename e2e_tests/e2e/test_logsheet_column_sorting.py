"""
E2E tests for logsheet management page column sorting (Duration, Time, Status).

These tests exercise the user-visible JavaScript behavior fixed in Issue #909:
the custom ``duration``/``time``/``status`` Tablesort comparators in
``logsheet_manage.html`` must sort the numeric ``data-sort`` values numerically
in both ascending and descending directions, rather than treating every cell
as ``0`` (the previous no-op bug caused by calling ``.getAttribute()`` on an
already-extracted value string).

Setup notes
-----------
We use an **unfinalized** logsheet dated *tomorrow*.  An in-flight flight
carries a ``live-duration`` element whose ``data-sort`` is rewritten in place
every 30 s by ``updateLiveDurations()``.  When the launch timestamp is in the
future, that updater pins ``data-sort`` to the stable ``"999999"`` in-air
sentinel (see ``logsheet_manage.html``), so all ``data-sort`` values remain
stable for the duration of the test.  This lets us assert deterministic row
order while still exercising a realistic mix of landed / in-flight / pending
flights (status 3 / 2 / 1).
"""

from datetime import date, time, timedelta

from logsheet.models import Airfield, Flight, Glider, Logsheet
from siteconfig.models import SiteConfiguration

from .conftest import DjangoPlaywrightTestCase


class TestLogsheetColumnSortingE2E(DjangoPlaywrightTestCase):
    """Verify numeric sorting of the Duration/Time/Status columns on the manage page."""

    def setUp(self):
        super().setUp()

        SiteConfiguration.objects.all().delete()
        SiteConfiguration.objects.create(
            club_name="Test Club",
            domain_name="test.org",
            club_abbreviation="TC",
        )

        self.duty_officer = self.create_test_member(
            username="do_colsort",
            first_name="Duty",
            last_name="Officer",
        )

        self.pilot_a = self.create_test_member(
            username="pilot_a_colsort", first_name="Alpha", last_name="Pilot"
        )
        self.pilot_b = self.create_test_member(
            username="pilot_b_colsort", first_name="Bravo", last_name="Pilot"
        )
        self.pilot_c = self.create_test_member(
            username="pilot_c_colsort", first_name="Charlie", last_name="Pilot"
        )
        self.pilot_d = self.create_test_member(
            username="pilot_d_colsort", first_name="Delta", last_name="Pilot"
        )
        self.pilot_e = self.create_test_member(
            username="pilot_e_colsort", first_name="Echo", last_name="Pilot"
        )

        self.airfield = Airfield.objects.create(identifier="E2EC", name="E2E Colsort")
        self.glider = Glider.objects.create(
            make="Schleicher",
            model="ASK-21",
            n_number="N779E2C",
            competition_number="E2C",
            seats=2,
            is_active=True,
        )

        # Dated tomorrow so the in-flight flight's launch is in the future and
        # the live-duration updater keeps its data-sort pinned to "999999".
        self.logsheet = Logsheet.objects.create(
            log_date=date.today() + timedelta(days=1),
            airfield=self.airfield,
            created_by=self.duty_officer,
            duty_officer=self.duty_officer,
        )

        # Flight 1 — landed, launch 09:00 (HHMM 0900), duration 00:30 -> 1800s
        Flight.objects.create(
            logsheet=self.logsheet,
            airfield=self.airfield,
            pilot=self.pilot_a,
            glider=self.glider,
            flight_type="solo",
            launch_time=time(9, 0),
            landing_time=time(9, 30),
        )

        # Flight 2 — landed, launch 08:15 (HHMM 0815), duration 00:10 -> 600s
        Flight.objects.create(
            logsheet=self.logsheet,
            airfield=self.airfield,
            pilot=self.pilot_b,
            glider=self.glider,
            flight_type="solo",
            launch_time=time(8, 15),
            landing_time=time(8, 25),
        )

        # Flight 3 — landed, launch 10:45 (HHMM 1045), duration 01:10 -> 4200s
        Flight.objects.create(
            logsheet=self.logsheet,
            airfield=self.airfield,
            pilot=self.pilot_c,
            glider=self.glider,
            flight_type="solo",
            launch_time=time(10, 45),
            landing_time=time(11, 55),
        )

        # Flight 4 — in-flight: status 2, time 0750, duration "999999" (pinned)
        Flight.objects.create(
            logsheet=self.logsheet,
            airfield=self.airfield,
            pilot=self.pilot_d,
            glider=self.glider,
            flight_type="solo",
            launch_time=time(7, 50),
        )

        # Flight 5 — pending (not launched): status 1, time "0000", duration 0
        Flight.objects.create(
            logsheet=self.logsheet,
            airfield=self.airfield,
            pilot=self.pilot_e,
            glider=self.glider,
            flight_type="solo",
        )

    def _header(self, column_class):
        return self.page.locator(f".flights-table th.{column_class}")

    def _data_sort_values(self, column_class):
        return self.page.eval_on_selector_all(
            f".flights-table tbody tr.flight-row td.{column_class}",
            "cells => cells.map(c => c.getAttribute('data-sort'))",
        )

    def _click_header_and_wait_sort_change(self, header):
        before = header.get_attribute("aria-sort")
        handle = header.element_handle()
        assert handle is not None
        header.click()
        self.page.wait_for_function(
            """
            ({ el, previous }) => {
                const current = el ? el.getAttribute('aria-sort') : null;
                return current !== null && current !== previous;
            }
            """,
            arg={"el": handle, "previous": before},
        )

    def _is_sorted(self, values, ascending):
        nums = [int(v) for v in values]
        expected = sorted(nums) if ascending else sorted(nums, reverse=True)
        return nums == expected

    def _normalize_to_ascending(self, header, column_class, expected_set):
        """Click the header (up to twice) until the column is ascending."""
        self._click_header_and_wait_sort_change(header)
        if not self._is_sorted(self._data_sort_values(column_class), ascending=True):
            self._click_header_and_wait_sort_change(header)

    def test_duration_sorts_numerically_both_directions(self):
        self.login(username="do_colsort")
        self.page.goto(f"{self.live_server_url}/logsheet/manage/{self.logsheet.pk}/")
        self.page.wait_for_load_state("networkidle")

        hdr = self._header("duration-col")
        assert hdr.count() == 1

        expected = {0, 600, 1800, 4200, 999999}

        self._normalize_to_ascending(hdr, "duration-col", expected)
        asc = self._data_sort_values("duration-col")
        assert set(int(v) for v in asc) == expected, f"Unexpected duration set: {asc}"
        assert self._is_sorted(asc, ascending=True), f"Duration asc unsorted: {asc}"

        self._click_header_and_wait_sort_change(hdr)
        desc = self._data_sort_values("duration-col")
        assert self._is_sorted(desc, ascending=False), f"Duration desc unsorted: {desc}"

    def test_time_sorts_numerically_both_directions(self):
        self.login(username="do_colsort")
        self.page.goto(f"{self.live_server_url}/logsheet/manage/{self.logsheet.pk}/")

        header = self._header("time-col")
        assert header.count() == 1

        expected = {0, 750, 815, 900, 1045}  # 0 = pending, 750 = in-flight 07:50

        self._normalize_to_ascending(header, "time-col", expected)
        asc = self._data_sort_values("time-col")
        assert set(int(v) for v in asc) == expected, f"Unexpected time set: {asc}"
        assert self._is_sorted(asc, ascending=True), f"Time asc unsorted: {asc}"

        self._click_header_and_wait_sort_change(header)
        desc = self._data_sort_values("time-col")
        assert self._is_sorted(desc, ascending=False), f"Time desc unsorted: {desc}"

    def test_status_sorts_numerically_both_directions(self):
        self.login(username="do_colsort")
        self.page.goto(f"{self.live_server_url}/logsheet/manage/{self.logsheet.pk}/")

        header = self._header("status-col")
        assert header.count() == 1

        expected = {1, 2, 3}  # pending, in-flight, landed

        self._normalize_to_ascending(header, "status-col", expected)
        asc = self._data_sort_values("status-col")
        assert set(int(v) for v in asc) == expected, f"Unexpected status set: {asc}"
        assert self._is_sorted(asc, ascending=True), f"Status asc unsorted: {asc}"

        self._click_header_and_wait_sort_change(header)
        desc = self._data_sort_values("status-col")
        assert self._is_sorted(desc, ascending=False), f"Status desc unsorted: {desc}"
