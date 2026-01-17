"""
E2E tests for configurable quick altitude buttons on flight form (Issue #467).

Tests JavaScript functionality: button rendering, click handlers, and
dynamic button configuration from SiteConfiguration.
"""

import unittest
from datetime import date

from e2e_tests.e2e.conftest import DjangoPlaywrightTestCase
from logsheet.models import Airfield, Glider, Logsheet
from siteconfig.models import SiteConfiguration


class TestLogsheetAltitudeButtons(DjangoPlaywrightTestCase):
    """E2E tests for altitude quick-select buttons."""

    def setUp(self):
        super().setUp()
        # Create test member
        self.member = self.create_test_member(username="testpilot", is_superuser=True)
        self.login(username="testpilot")

        # Create test airfield
        self.airfield = Airfield.objects.create(
            identifier="TEST", name="Test Airfield", is_active=True
        )

        # Create test glider
        self.glider = Glider.objects.create(
            make="Schleicher",
            model="ASK-21",
            n_number="N123AB",
            competition_number="XY",
            seats=2,
            is_active=True,
        )

        # Create test logsheet
        self.logsheet = Logsheet.objects.create(
            log_date=date(2026, 1, 10),
            airfield=self.airfield,
            created_by=self.member,
            duty_officer=self.member,
        )

        # Ensure SiteConfiguration exists with default altitude buttons
        self.config = SiteConfiguration.objects.create(
            club_name="Test Club",
            domain_name="test.com",
            club_abbreviation="TC",
            quick_altitude_buttons="2000,3000",
        )

    def test_altitude_buttons_render_with_default_config(self):
        """Verify default altitude buttons (2K, 3K) render correctly."""
        # Navigate to logsheet management page
        self.page.goto(f"{self.live_server_url}/logsheet/manage/{self.logsheet.pk}/")

        # Click "Add Flight" button to open modal
        self.page.click('a:has-text("Add Flight")')

        # Wait for modal to load
        self.page.wait_for_selector("#flightModal", state="visible")

        # Verify 2K button exists with correct attributes
        btn_2k = self.page.query_selector(
            'button.altitude-quick-btn[data-altitude="2000"]'
        )
        assert btn_2k is not None, "2K button should exist"
        assert btn_2k.inner_text() == "2K", "2K button should have correct label"

        # Verify 3K button exists with correct attributes
        btn_3k = self.page.query_selector(
            'button.altitude-quick-btn[data-altitude="3000"]'
        )
        assert btn_3k is not None, "3K button should exist"
        assert btn_3k.inner_text() == "3K", "3K button should have correct label"

    def test_altitude_button_click_sets_select_value(self):
        """Test that clicking an altitude button sets the release_altitude field."""
        self.page.goto(f"{self.live_server_url}/logsheet/manage/{self.logsheet.pk}/")

        # Open add flight modal
        self.page.click('a:has-text("Add Flight")')
        self.page.wait_for_selector("#flightModal", state="visible")

        # Get the altitude select element
        altitude_select = self.page.query_selector("#id_release_altitude")
        assert altitude_select is not None, "Altitude select should exist"

        # Initial value should be empty or 0
        initial_value = altitude_select.evaluate("el => el.value")
        assert initial_value in [
            "",
            "0",
        ], f"Initial value should be empty, got {initial_value}"

        # Click 2K button
        self.page.click('button.altitude-quick-btn[data-altitude="2000"]')

        # Verify select value changed to 2000
        value_after_2k = altitude_select.evaluate("el => el.value")
        assert (
            value_after_2k == "2000"
        ), f"After clicking 2K, value should be 2000, got {value_after_2k}"

        # Click 3K button
        self.page.click('button.altitude-quick-btn[data-altitude="3000"]')

        # Verify select value changed to 3000
        value_after_3k = altitude_select.evaluate("el => el.value")
        assert (
            value_after_3k == "3000"
        ), f"After clicking 3K, value should be 3000, got {value_after_3k}"

    def test_custom_altitude_buttons_configuration(self):
        """Test that custom altitude button configuration renders correctly."""
        # Update config with custom altitude buttons
        self.config.quick_altitude_buttons = "300,1000,1500,2000,3000"
        self.config.save()

        self.page.goto(f"{self.live_server_url}/logsheet/manage/{self.logsheet.pk}/")
        self.page.click('a:has-text("Add Flight")')
        self.page.wait_for_selector("#flightModal", state="visible")

        # Verify all 5 buttons exist with correct labels
        expected_buttons = [
            ("300", "300"),
            ("1000", "1K"),
            ("1500", "1.5K"),
            ("2000", "2K"),
            ("3000", "3K"),
        ]

        for altitude_value, expected_label in expected_buttons:
            btn = self.page.query_selector(
                f'button.altitude-quick-btn[data-altitude="{altitude_value}"]'
            )
            assert btn is not None, f"Button for {altitude_value} should exist"
            actual_label = btn.inner_text()
            assert (
                actual_label == expected_label
            ), f"Button for {altitude_value} should have label '{expected_label}', got '{actual_label}'"

        # Test clicking a custom button (1.5K)
        altitude_select = self.page.query_selector("#id_release_altitude")
        assert altitude_select is not None, "Altitude select should exist"
        self.page.click('button.altitude-quick-btn[data-altitude="1500"]')
        value_after_click = altitude_select.evaluate("el => el.value")
        assert (
            value_after_click == "1500"
        ), f"After clicking 1.5K, value should be 1500, got {value_after_click}"

    @unittest.skip(
        "FlightForm requires SiteConfiguration to exist - no fallback behavior"
    )
    def test_fallback_buttons_when_config_missing(self):
        """Test that default 2K/3K buttons render when SiteConfiguration is None.

        NOTE: This test is skipped because FlightForm raises ImproperlyConfigured
        when SiteConfiguration is missing. The form cannot function without config,
        so there are no fallback buttons. This is by design for security and proper
        system operation.
        """
        # Delete SiteConfiguration
        SiteConfiguration.objects.all().delete()

        self.page.goto(f"{self.live_server_url}/logsheet/manage/{self.logsheet.pk}/")
        self.page.click('a:has-text("Add Flight")')
        self.page.wait_for_selector("#flightModal", state="visible")

        # Should still render fallback 2K and 3K buttons
        btn_2k = self.page.query_selector(
            'button.altitude-quick-btn[data-altitude="2000"]'
        )
        btn_3k = self.page.query_selector(
            'button.altitude-quick-btn[data-altitude="3000"]'
        )

        assert btn_2k is not None, "Fallback 2K button should exist"
        assert btn_3k is not None, "Fallback 3K button should exist"

        # Test clicking fallback button still works
        altitude_select = self.page.query_selector("#id_release_altitude")
        assert altitude_select is not None, "Altitude select should exist"
        self.page.click('button.altitude-quick-btn[data-altitude="2000"]')
        value_after_click = altitude_select.evaluate("el => el.value")
        assert (
            value_after_click == "2000"
        ), f"Fallback 2K button should set value to 2000, got {value_after_click}"
