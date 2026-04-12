"""
E2E tests for the Analytics Dashboard (Issue #721).

Tests Bootstrap 5 migration, mobile viewport layout, chart container sizing,
and JS download-button interactions.
"""

from e2e_tests.e2e.conftest import DjangoPlaywrightTestCase


class TestAnalyticsDashboardE2E(DjangoPlaywrightTestCase):
    """E2E tests for the analytics dashboard page."""

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    def _go_to_analytics(self):
        """Navigate to the analytics dashboard."""
        self.page.goto(f"{self.live_server_url}/analytics/")
        # Wait for Chart.js bundle to load (it's deferred)
        self.page.wait_for_load_state("networkidle", timeout=10_000)

    # ------------------------------------------------------------------ #
    # Tests                                                                #
    # ------------------------------------------------------------------ #

    def test_page_loads_for_authenticated_member(self):
        """Analytics page loads without errors for an authenticated member."""
        self.create_test_member(username="analyst")
        self.login(username="analyst")

        self._go_to_analytics()

        # Title is present
        title = self.page.locator("h2", has_text="Operations Analytics")
        assert title.is_visible(), "Page heading not found"

        # No Django error page
        body_text = self.page.inner_text("body")
        assert "Server Error" not in body_text
        assert "Exception Value" not in body_text

    def test_chart_canvases_present(self):
        """All expected chart canvas elements are rendered."""
        self.create_test_member(username="analyst")
        self.login(username="analyst")
        self._go_to_analytics()

        expected_canvas_ids = [
            "cumuChart",
            "byAcftChart",
            "timeOpsChart",
            "utilChart",
            "utilPrivChart",
            "fdChart",
            "pgfChart",
            "durChart",
            "instChart",
            "towChart",
            "long3hChart",
            "dutyChart",
            "towSchedChart",
            "instSchedChart",
            "combinedDutyChart",
        ]
        for canvas_id in expected_canvas_ids:
            canvas = self.page.locator(f"#{canvas_id}")
            assert canvas.count() == 1, f"Canvas #{canvas_id} missing from page"

    def test_chart_download_buttons_present(self):
        """Each chart card contains PNG / SVG / CSV download buttons."""
        self.create_test_member(username="analyst")
        self.login(username="analyst")
        self._go_to_analytics()

        # There should be 3 × (number of charts) = 45 download buttons total
        download_buttons = self.page.locator("button.chart-dl")
        count = download_buttons.count()
        assert count > 0, "No chart download buttons found"
        # Each chart card contributes 3 buttons (PNG, SVG, CSV)
        assert count % 3 == 0, f"Expected groups of 3 download buttons, got {count}"

    def test_annual_range_form_visible(self):
        """The year-range filter form is present and has the expected inputs."""
        self.create_test_member(username="analyst")
        self.login(username="analyst")
        self._go_to_analytics()

        form = self.page.locator("#annual-range")
        assert form.is_visible(), "Annual range form not visible"

        start_input = form.locator("input[name='start']")
        end_input = form.locator("input[name='end']")
        assert start_input.count() == 1, "Start year input missing"
        assert end_input.count() == 1, "End year input missing"

    def test_date_range_form_visible(self):
        """The date-range filter form inside the info alert is present."""
        self.create_test_member(username="analyst")
        self.login(username="analyst")
        self._go_to_analytics()

        form = self.page.locator("#date-range form")
        assert form.count() == 1, "Date-range form not found"

        util_start = form.locator("input[name='util_start']")
        util_end = form.locator("input[name='util_end']")
        assert util_start.count() == 1, "util_start date input missing"
        assert util_end.count() == 1, "util_end date input missing"

    def test_no_horizontal_overflow_on_mobile_viewport(self):
        """Page does not overflow horizontally at 390px (iPhone 12 width)."""
        self.create_test_member(username="analyst")
        self.login(username="analyst")

        # Set mobile viewport
        self.page.set_viewport_size({"width": 390, "height": 844})
        self._go_to_analytics()

        # document.documentElement.scrollWidth should not exceed the viewport width
        scroll_width = self.page.evaluate("document.documentElement.scrollWidth")
        viewport_width = self.page.evaluate("window.innerWidth")
        assert scroll_width <= viewport_width, (
            f"Horizontal overflow detected: scrollWidth={scroll_width}px "
            f"> viewportWidth={viewport_width}px"
        )

    def test_chart_containers_have_nonzero_height_on_mobile(self):
        """Chart containers are visible with non-zero height on a mobile viewport."""
        self.create_test_member(username="analyst")
        self.login(username="analyst")

        self.page.set_viewport_size({"width": 390, "height": 844})
        self._go_to_analytics()

        # Check the first chart box
        chart_box = self.page.locator(".chart-box").first
        assert chart_box.is_visible(), "First .chart-box is not visible on mobile"

        bounding_box = chart_box.bounding_box()
        assert bounding_box is not None, "Could not get bounding box of chart-box"
        assert (
            bounding_box["height"] > 0
        ), f"Chart box has zero height on mobile: {bounding_box}"

    def test_no_horizontal_overflow_on_pixel_viewport(self):
        """Page does not overflow horizontally at 412px (Pixel 9 width)."""
        self.create_test_member(username="analyst")
        self.login(username="analyst")

        self.page.set_viewport_size({"width": 412, "height": 915})
        self._go_to_analytics()

        scroll_width = self.page.evaluate("document.documentElement.scrollWidth")
        viewport_width = self.page.evaluate("window.innerWidth")
        assert scroll_width <= viewport_width, (
            f"Horizontal overflow at 412px: scrollWidth={scroll_width}px "
            f"> viewportWidth={viewport_width}px"
        )

    def test_time_ops_tooltip_title_includes_year_context(self):
        """Time of day tooltip title includes selected year range context."""
        from datetime import date, time

        from logsheet.models import Airfield, Flight, Glider, Logsheet

        analyst = self.create_test_member(username="analyst")
        self.login(username="analyst")

        airfield = Airfield.objects.create(identifier="KFRR", name="Front Royal")
        glider = Glider.objects.create(
            make="Schleicher",
            model="ASK-21",
            n_number="N839UX",
            competition_number="21",
            seats=2,
            is_active=True,
            club_owned=True,
        )
        logsheet = Logsheet.objects.create(
            log_date=date.today(),
            airfield=airfield,
            created_by=analyst,
            finalized=True,
        )
        Flight.objects.create(
            logsheet=logsheet,
            pilot=analyst,
            glider=glider,
            launch_time=time(10, 0),
            landing_time=time(10, 35),
            launch_method="tow",
            release_altitude=3000,
        )

        self._go_to_analytics()

        start_year = self.page.input_value("#annual-range input[name='start']")
        end_year = self.page.input_value("#annual-range input[name='end']")

        tooltip_title = self.page.evaluate(
            """() => {
              const cb = window.timeOpsChart?.options?.plugins?.tooltip?.callbacks?.title;
              if (!cb) return "";
              return cb([{ parsed: { x: 32 } }]);
            }"""
        )

        assert tooltip_title, "Expected tooltip title callback output"
        assert start_year in tooltip_title
        if start_year != end_year:
            assert end_year in tooltip_title
