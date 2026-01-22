"""
E2E tests for duty preference percentage validation JavaScript.

Issue #540: Verify JavaScript correctly validates duty percentage totals
and shows appropriate UI feedback for rounding cases (33% + 66% = 99%).
"""

from .conftest import DjangoPlaywrightTestCase


class TestDutyPercentageValidation(DjangoPlaywrightTestCase):
    """Test JavaScript validation of duty percentage totals in blackout calendar."""

    def test_99_percent_shows_success(self):
        """Test that 33% + 66% = 99% shows success message (green)."""
        # Create a member with instructor and towpilot roles
        _ = self.create_test_member(
            username="testpilot",
            email="test@example.com",
            instructor=True,
            towpilot=True,
        )
        self.login(username="testpilot")

        # Navigate to blackout calendar
        self.page.goto(f"{self.live_server_url}/duty_roster/blackout/")

        # Find the percentage dropdowns
        instructor_select = self.page.locator('select[name="instructor_percent"]')
        towpilot_select = self.page.locator('select[name="towpilot_percent"]')

        # Select 33% instructor, 66% towpilot (= 99%)
        instructor_select.select_option("33")
        towpilot_select.select_option("66")

        # Wait for JavaScript to update the UI by waiting for the alert to be visible
        self.page.locator("#percentageAlert").wait_for(state="visible")

        # Check that the alert has success styling (green)
        alert = self.page.locator("#percentageAlert")
        assert alert.is_visible(), "Percentage alert should be visible"

        # Verify it has the success class (green)
        alert_classes = alert.get_attribute("class") or ""
        assert (
            "alert-success" in alert_classes
        ), f"Alert should have success class for 99%, got: {alert_classes}"

        # Verify the status text shows success
        status = self.page.locator("#percentageStatus")
        status_text = status.text_content() or ""
        assert (
            "scheduled for duty" in status_text.lower()
        ), f"Should show scheduled message, got: {status_text}"

    def test_100_percent_shows_success(self):
        """Test that exactly 100% shows success message (green)."""
        _ = self.create_test_member(
            username="testpilot",
            email="test@example.com",
            instructor=True,
            towpilot=True,
        )
        self.login(username="testpilot")

        self.page.goto(f"{self.live_server_url}/duty_roster/blackout/")

        # Select 25% instructor, 75% towpilot (= 100%)
        instructor_select = self.page.locator('select[name="instructor_percent"]')
        towpilot_select = self.page.locator('select[name="towpilot_percent"]')

        instructor_select.select_option("25")
        towpilot_select.select_option("75")

        # Wait for JavaScript to update the UI
        self.page.locator("#percentageAlert").wait_for(state="visible")

        # Verify success styling
        alert = self.page.locator("#percentageAlert")
        alert_classes = alert.get_attribute("class") or ""
        assert (
            "alert-success" in alert_classes
        ), f"Alert should have success class for 100%, got: {alert_classes}"

        # Verify the total displays correctly
        total = self.page.locator("#percentageTotal")
        total_text = total.text_content() or ""
        assert "100%" in total_text, f"Should show 100%, got: {total_text}"

    def test_below_valid_range_shows_error(self):
        """Test that total below 99% (e.g., 75%) shows error message (red)."""
        _ = self.create_test_member(
            username="testpilot",
            email="test@example.com",
            instructor=True,
            towpilot=True,
        )
        self.login(username="testpilot")

        self.page.goto(f"{self.live_server_url}/duty_roster/blackout/")

        # Select 25% + 50% = 75% (below valid range)
        # Note: dropdown options are [0, 25, 33, 50, 66, 75, 100]
        # We can't select exactly 98%, so test with 75% as proxy for "below 99%"
        instructor_select = self.page.locator('select[name="instructor_percent"]')
        towpilot_select = self.page.locator('select[name="towpilot_percent"]')

        instructor_select.select_option("25")
        towpilot_select.select_option("50")

        # Wait for JavaScript to update the UI
        self.page.locator("#percentageAlert").wait_for(state="visible")

        # Verify error styling for below-range total
        alert = self.page.locator("#percentageAlert")
        alert_classes = alert.get_attribute("class") or ""
        assert (
            "alert-danger" in alert_classes
        ), f"Alert should have danger class for 75%, got: {alert_classes}"

        # Verify error message
        status = self.page.locator("#percentageStatus")
        status_text = status.text_content() or ""
        assert (
            "99-100%" in status_text or "must equal" in status_text.lower()
        ), f"Should show error message, got: {status_text}"

    def test_above_valid_range_shows_error(self):
        """Test that total above 100% (e.g., 125%) shows error message (red)."""
        _ = self.create_test_member(
            username="testpilot",
            email="test@example.com",
            instructor=True,
            towpilot=True,
            duty_officer=True,
        )
        self.login(username="testpilot")

        self.page.goto(f"{self.live_server_url}/duty_roster/blackout/")

        # With 3 roles, we can get over 100%
        # Select 50% + 50% + 25% = 125% (above valid range)
        instructor_select = self.page.locator('select[name="instructor_percent"]')
        towpilot_select = self.page.locator('select[name="towpilot_percent"]')
        do_select = self.page.locator('select[name="duty_officer_percent"]')

        instructor_select.select_option("50")
        towpilot_select.select_option("50")
        do_select.select_option("25")

        # Wait for JavaScript to update the UI
        self.page.locator("#percentageAlert").wait_for(state="visible")

        # Verify error styling for above-range total
        alert = self.page.locator("#percentageAlert")
        alert_classes = alert.get_attribute("class") or ""
        assert (
            "alert-danger" in alert_classes
        ), f"Alert should have danger class for 125%, got: {alert_classes}"

        # Verify total shows the actual percentage
        total = self.page.locator("#percentageTotal")
        total_text = total.text_content() or ""
        assert "125%" in total_text, f"Should show 125%, got: {total_text}"

    def test_zero_percent_shows_info(self):
        """Test that 0% shows info message (blue) - not scheduled."""
        _ = self.create_test_member(
            username="testpilot",
            email="test@example.com",
            instructor=True,
            towpilot=True,
        )
        self.login(username="testpilot")

        self.page.goto(f"{self.live_server_url}/duty_roster/blackout/")

        # Select 0% for all roles
        instructor_select = self.page.locator('select[name="instructor_percent"]')
        towpilot_select = self.page.locator('select[name="towpilot_percent"]')

        instructor_select.select_option("0")
        towpilot_select.select_option("0")

        # Wait for JavaScript to update the UI
        self.page.locator("#percentageAlert").wait_for(state="visible")

        # Verify info styling (blue)
        alert = self.page.locator("#percentageAlert")
        alert_classes = alert.get_attribute("class") or ""
        assert (
            "alert-info" in alert_classes
        ), f"Alert should have info class for 0%, got: {alert_classes}"

        # Verify message says not scheduled
        status = self.page.locator("#percentageStatus")
        status_text = status.text_content() or ""
        assert (
            "not be scheduled" in status_text.lower()
        ), f"Should show not scheduled message, got: {status_text}"

    def test_form_submission_with_99_percent(self):
        """Test that form can be submitted with 99% total."""
        _ = self.create_test_member(
            username="testpilot",
            email="test@example.com",
            instructor=True,
            towpilot=True,
        )
        self.login(username="testpilot")

        self.page.goto(f"{self.live_server_url}/duty_roster/blackout/")

        # Set 33% + 66% = 99%
        instructor_select = self.page.locator('select[name="instructor_percent"]')
        towpilot_select = self.page.locator('select[name="towpilot_percent"]')

        instructor_select.select_option("33")
        towpilot_select.select_option("66")

        # Wait for JavaScript to update the UI
        self.page.locator("#percentageAlert").wait_for(state="visible")

        # Submit the form (use more specific locator to avoid logout button)
        submit_button = self.page.locator('button[type="submit"].btn-success')
        submit_button.click()

        # Wait for page to reload/redirect
        self.page.wait_for_load_state("networkidle")

        # Verify a success flash message appears indicating preferences were saved
        # and that no error message is shown after the redirect.
        error_alerts = self.page.locator(".alert-danger")
        assert (
            error_alerts.count() == 0
        ), "No error alerts should be shown after successful submission"

        # Check for Django success message specifically about duty preferences being saved
        success_alerts = self.page.locator(".alert-success")
        success_texts = success_alerts.all_text_contents()
        success_texts_lower = [text.lower() for text in success_texts]
        assert any(
            "duty preferences saved" in text for text in success_texts_lower
        ), f"Expected success message indicating duty preferences were saved, got: {success_texts}"
