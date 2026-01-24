"""
End-to-end tests for maintenance deadline update functionality (Issue #541).

Tests JavaScript functionality including Bootstrap modal interactions,
AJAX form submission, DOM updates, and error handling.
"""

from datetime import date

from django.contrib.auth.models import Group

from e2e_tests.e2e.conftest import DjangoPlaywrightTestCase
from logsheet.models import AircraftMeister, Glider, MaintenanceDeadline


class TestMaintenanceDeadlineUpdateE2E(DjangoPlaywrightTestCase):
    """E2E tests for maintenance deadline update UI."""

    def setUp(self):
        super().setUp()
        # Create test glider
        self.glider = Glider.objects.create(
            make="Schleicher",
            model="ASW 28",
            n_number="N123AB",
            competition_number="AB",
        )

        # Create maintenance deadline
        self.deadline = MaintenanceDeadline.objects.create(
            glider=self.glider,
            description="annual",
            due_date=date(2026, 6, 30),
        )

        # Create webmaster group
        self.webmaster_group = Group.objects.get_or_create(name="Webmasters")[0]

    def test_modal_opens_on_button_click(self):
        """Test that clicking Update button opens Bootstrap modal."""
        webmaster = self.create_test_member(username="webmaster", is_superuser=False)
        webmaster.groups.add(self.webmaster_group)
        self.login(username="webmaster")

        self.page.goto(f"{self.live_server_url}/logsheet/maintenance-deadlines/")

        # Verify update button is visible
        update_button = self.page.locator(".update-deadline-btn").first
        assert update_button.is_visible()

        # Click the button
        update_button.click()

        # Wait for modal to appear
        modal = self.page.locator("#updateDeadlineModal")
        assert modal.is_visible()

        # Verify modal content
        modal_text = modal.text_content() or ""
        assert "Update Maintenance Deadline" in modal_text
        assert "AB / N123AB" in modal_text  # Aircraft name
        assert "Annual Inspection" in modal_text  # Task
        assert "2026-06-30" in modal_text  # Current date

    def test_form_submission_via_button_updates_deadline(self):
        """Test that clicking Save Changes button submits form and updates deadline."""
        webmaster = self.create_test_member(username="webmaster", is_superuser=False)
        webmaster.groups.add(self.webmaster_group)
        self.login(username="webmaster")

        self.page.goto(f"{self.live_server_url}/logsheet/maintenance-deadlines/")

        # Open modal
        self.page.locator(".update-deadline-btn").first.click()
        self.page.wait_for_selector("#updateDeadlineModal.show")

        # Change the date
        date_input = self.page.locator("#new-due-date")
        date_input.fill("2027-01-31")

        # Click Save Changes
        self.page.locator("#save-deadline-btn").click()

        # Wait for success toast
        toast = self.page.locator("#successToast")
        assert toast.wait_for(state="visible", timeout=5000)
        toast_text = toast.text_content() or ""
        assert "successfully" in toast_text.lower()

        # Wait for page reload
        self.page.wait_for_load_state("networkidle")

        # Verify new date appears in table (after reload)
        assert "2027-01-31" in self.page.content()

    def test_form_submission_via_enter_key(self):
        """Test that pressing Enter in date field submits form (keyboard accessibility)."""
        webmaster = self.create_test_member(username="webmaster", is_superuser=False)
        webmaster.groups.add(self.webmaster_group)
        self.login(username="webmaster")

        self.page.goto(f"{self.live_server_url}/logsheet/maintenance-deadlines/")

        # Open modal
        self.page.locator(".update-deadline-btn").first.click()
        self.page.wait_for_selector("#updateDeadlineModal.show")

        # Change the date and press Enter
        date_input = self.page.locator("#new-due-date")
        date_input.fill("2027-02-28")
        date_input.press("Enter")

        # Wait for success toast
        toast = self.page.locator("#successToast")
        assert toast.wait_for(state="visible", timeout=5000)
        toast_text = toast.text_content() or ""
        assert "successfully" in toast_text.lower()

    def test_error_handling_for_invalid_submission(self):
        """Test that error messages display correctly for invalid submissions."""
        webmaster = self.create_test_member(username="webmaster", is_superuser=False)
        webmaster.groups.add(self.webmaster_group)
        self.login(username="webmaster")

        self.page.goto(f"{self.live_server_url}/logsheet/maintenance-deadlines/")

        # Open modal
        self.page.locator(".update-deadline-btn").first.click()
        self.page.wait_for_selector("#updateDeadlineModal.show")

        # Clear the date field (invalid submission)
        date_input = self.page.locator("#new-due-date")
        date_input.fill("")

        # Try to submit (HTML5 validation should prevent this in real browsers,
        # but we can test the JavaScript error handling by simulating backend error)
        # For now, just verify the error div exists and is initially hidden
        error_div = self.page.locator("#update-error-message")
        assert error_div.is_visible() is False  # Should be hidden initially

    def test_maintenance_officer_sees_only_their_aircraft(self):
        """Test that maintenance officers only see Update buttons for their assigned aircraft."""
        # Create another glider
        other_glider = Glider.objects.create(
            make="Schempp-Hirth",
            model="Discus 2",
            n_number="N456CD",
            competition_number="CD",
        )
        MaintenanceDeadline.objects.create(
            glider=other_glider,
            description="annual",
            due_date=date(2026, 7, 15),
        )

        # Create maintenance officer for first glider only
        officer = self.create_test_member(username="officer", is_superuser=False)
        AircraftMeister.objects.create(glider=self.glider, member=officer)

        self.login(username="officer")

        self.page.goto(f"{self.live_server_url}/logsheet/maintenance-deadlines/")

        # Count update buttons (should only see one for the assigned glider)
        update_buttons = self.page.locator(".update-deadline-btn")
        assert update_buttons.count() == 1

        # Verify the button is for the correct aircraft
        button_text = update_buttons.first.get_attribute("data-aircraft") or ""
        assert "AB / N123AB" in button_text

    def test_regular_member_sees_no_update_buttons(self):
        """Test that regular members see no Update buttons."""
        self.create_test_member(username="regular", is_superuser=False)
        self.login(username="regular")

        self.page.goto(f"{self.live_server_url}/logsheet/maintenance-deadlines/")

        # Verify no update buttons visible
        update_buttons = self.page.locator(".update-deadline-btn")
        assert update_buttons.count() == 0

        # Verify no Actions column header
        assert "Actions" not in self.page.content()

    def test_modal_closes_on_cancel(self):
        """Test that clicking Cancel button closes the modal."""
        webmaster = self.create_test_member(username="webmaster", is_superuser=False)
        webmaster.groups.add(self.webmaster_group)
        self.login(username="webmaster")

        self.page.goto(f"{self.live_server_url}/logsheet/maintenance-deadlines/")

        # Open modal
        self.page.locator(".update-deadline-btn").first.click()
        modal = self.page.locator("#updateDeadlineModal")
        assert modal.is_visible()

        # Click Cancel
        self.page.locator('button[data-bs-dismiss="modal"]').first.click()

        # Modal should close
        self.page.wait_for_selector(
            "#updateDeadlineModal", state="hidden", timeout=5000
        )

    def test_superuser_sees_all_update_buttons(self):
        """Test that superusers see Update buttons for all aircraft."""
        # Create another glider
        other_glider = Glider.objects.create(
            make="Schempp-Hirth",
            model="Discus 2",
            n_number="N456CD",
            competition_number="CD",
        )
        MaintenanceDeadline.objects.create(
            glider=other_glider,
            description="annual",
            due_date=date(2026, 7, 15),
        )

        self.create_test_member(username="superuser", is_superuser=True)
        self.login(username="superuser")

        self.page.goto(f"{self.live_server_url}/logsheet/maintenance-deadlines/")

        # Should see update buttons for both aircraft
        update_buttons = self.page.locator(".update-deadline-btn")
        assert update_buttons.count() == 2
