"""
E2E tests for roster slot editing and diagnostics.

Issue #616: Verify JavaScript correctly handles clicking roster slots,
loading eligible members via AJAX, saving assignments, and displaying diagnostics.
"""

from datetime import datetime

from duty_roster.models import DutyPreference

from .conftest import DjangoPlaywrightTestCase


class TestRosterSlotEditing(DjangoPlaywrightTestCase):
    """Test JavaScript-driven roster slot editing functionality."""

    def setUp(self):
        """Set up test data for roster editing tests."""
        super().setUp()

        # Create rostermeister with appropriate permissions
        self.rostermeister = self.create_test_member(
            username="rostermeister",
            email="roster@example.com",
            instructor=True,
            towpilot=True,
            is_superuser=False,
            rostermeister=True,  # Set boolean flag for rostermeister permission
        )
        # Add to rostermeister group
        from django.contrib.auth.models import Group

        rostermeister_group, _ = Group.objects.get_or_create(name="rostermeister")
        self.rostermeister.groups.add(rostermeister_group)

        # Create some schedulable members
        self.member1 = self.create_test_member(
            username="pilot1",
            email="pilot1@example.com",
            instructor=True,
            towpilot=True,
        )
        self.member2 = self.create_test_member(
            username="pilot2",
            email="pilot2@example.com",
            instructor=True,
            towpilot=True,
        )

        # Create duty preferences for members
        DutyPreference.objects.create(
            member=self.member1,
            dont_schedule=False,
            max_assignments_per_month=8,
            instructor_percent=50,
            duty_officer_percent=0,
            ado_percent=0,
            towpilot_percent=50,
        )
        DutyPreference.objects.create(
            member=self.member2,
            dont_schedule=False,
            max_assignments_per_month=8,
            instructor_percent=50,
            duty_officer_percent=0,
            ado_percent=0,
            towpilot_percent=50,
        )

    def _create_test_roster(self):
        """Helper to create a test roster and navigate to propose page."""
        # Login as rostermeister
        self.login(username="rostermeister")

        # Navigate to propose-roster page with current month/year
        current_date = datetime.now()
        self.page.goto(
            f"{self.live_server_url}/duty_roster/propose-roster/?year={current_date.year}&month={current_date.month}"
        )

        # Ensure correct month/year are selected
        year_select = self.page.locator('select[name="year"]')
        month_select = self.page.locator('select[name="month"]')

        year_select.select_option(str(current_date.year))
        month_select.select_option(str(current_date.month))

        # Click roll button to generate roster
        roll_button = self.page.locator('button[name="action"][value="roll"]')
        roll_button.click()

        # Wait for roster to be created and page to be ready
        self.page.wait_for_url("**/duty_roster/propose-roster/**", timeout=10000)

    def test_clicking_empty_slot_shows_choice_modal(self):
        """Test that clicking an empty slot shows diagnostic/assign choice modal."""
        self._create_test_roster()

        # Find first empty slot
        empty_slots = self.page.locator(".empty-slot.editable-slot")
        assert empty_slots.count() > 0, "Test requires at least one empty slot"

        empty_slot = empty_slots.first
        empty_slot.click()

        # Wait for modal to appear
        modal = self.page.locator("#editSlotModal")
        modal.wait_for(state="visible", timeout=5000)

        # Verify choice buttons are present
        assign_btn = self.page.locator("#assignSlotFromChoiceBtn")
        diagnostic_btn = self.page.locator("#viewDiagnosticFromChoiceBtn")

        assert assign_btn.is_visible(), "Assign button should be visible"
        assert diagnostic_btn.is_visible(), "Diagnostic button should be visible"

        # Close modal for cleanup
        close_btn = self.page.locator("#editSlotModal .btn-close")
        close_btn.click()

    def test_clicking_filled_slot_shows_edit_modal(self):
        """Test that clicking a filled slot directly shows edit modal with members."""
        self._create_test_roster()

        # Find a filled slot
        filled_slots = self.page.locator(".editable-slot:not(.empty-slot)")
        assert filled_slots.count() > 0, "Test requires at least one filled slot"

        filled_slot = filled_slots.first
        filled_slot.click()

        # Wait for modal to appear
        modal = self.page.locator("#editSlotModal")
        modal.wait_for(state="visible", timeout=5000)

        # Wait for member select dropdown to appear (indicating AJAX completed)
        member_select = self.page.locator("#memberSelect")
        member_select.wait_for(state="visible", timeout=5000)

        assert member_select.is_visible(), "Member select should be visible"

        # Verify dropdown has options
        options = member_select.locator("option")
        assert options.count() > 1, "Should have at least empty option + members"

        # Close modal for cleanup
        close_btn = self.page.locator("#editSlotModal .btn-close")
        close_btn.click()

    def test_assigning_member_to_slot_updates_table(self):
        """Test that assigning a member via modal updates the roster table."""
        self._create_test_roster()

        # Find an empty slot to assign
        empty_slots = self.page.locator(".empty-slot.editable-slot")
        assert empty_slots.count() > 0, "Test requires at least one empty slot"

        empty_slot = empty_slots.first

        # Store original cell content
        original_content = empty_slot.text_content() or ""

        # Click slot
        empty_slot.click()

        # Wait for modal
        modal = self.page.locator("#editSlotModal")
        modal.wait_for(state="visible", timeout=5000)

        # If choice modal, click assign button
        assign_btn = self.page.locator("#assignSlotFromChoiceBtn")
        if assign_btn.is_visible():
            assign_btn.click()
            # Wait for edit modal to replace choice modal
            self.page.wait_for_timeout(500)

        # Wait for member select
        member_select = self.page.locator("#memberSelect")
        member_select.wait_for(state="visible", timeout=5000)

        # Select a member (first non-empty option)
        options = member_select.locator('option[value!=""]')
        assert options.count() > 0, "Test requires at least one eligible member"

        first_member_option = options.first
        member_value = first_member_option.get_attribute("value")
        member_name = first_member_option.text_content() or ""

        # Extract just the name part (before assignment count)
        member_name_only = member_name.split("[")[0].strip()

        member_select.select_option(member_value)

        # Click save button
        save_btn = self.page.locator("#saveSlotBtn")
        save_btn.click()

        # Wait for modal to close
        modal.wait_for(state="hidden", timeout=5000)

        # Verify cell content updated
        updated_content = empty_slot.text_content() or ""
        assert updated_content != original_content, "Cell content should have changed"
        assert (
            member_name_only in updated_content
        ), f"Cell should contain member name: {member_name_only}"

        # Verify cell no longer has empty-slot class
        cell_classes = empty_slot.get_attribute("class") or ""
        assert (
            "empty-slot" not in cell_classes
        ), "Cell should no longer be marked as empty"

    def test_viewing_diagnostics_shows_reasons(self):
        """Test that viewing diagnostics shows detailed reasons for empty slot."""
        self._create_test_roster()

        # Find an empty slot with diagnostics
        empty_slots_with_diagnostics = self.page.locator(
            ".empty-slot.editable-slot[data-diagnostic]"
        )
        assert (
            empty_slots_with_diagnostics.count() > 0
        ), "Test requires at least one empty slot with diagnostics"

        slot = empty_slots_with_diagnostics.first
        slot.click()

        # Wait for choice modal
        modal = self.page.locator("#editSlotModal")
        modal.wait_for(state="visible", timeout=5000)

        # Click diagnostic button
        diagnostic_btn = self.page.locator("#viewDiagnosticFromChoiceBtn")
        diagnostic_btn.click()

        # Wait for diagnostic modal to appear
        diagnostic_modal = self.page.locator("#diagnosticModal")
        diagnostic_modal.wait_for(state="visible", timeout=5000)

        # Verify diagnostic content is present
        diagnostic_body = self.page.locator("#diagnosticModalBody")
        diagnostic_text = diagnostic_body.text_content() or ""

        assert len(diagnostic_text) > 0, "Diagnostic modal should have content"
        # Check for common diagnostic elements
        assert (
            "Summary:" in diagnostic_text or "Total members" in diagnostic_text
        ), "Diagnostic should show summary or member count"

        # Close modal
        close_btn = self.page.locator("#diagnosticModal .btn-close")
        close_btn.click()

    def test_keyboard_navigation_enters_slot(self):
        """Test that keyboard Enter/Space key activates slot editing."""
        self._create_test_roster()

        # Find first editable slot
        editable_slots = self.page.locator(".editable-slot")
        assert editable_slots.count() > 0, "Test requires at least one editable slot"

        slot = editable_slots.first

        # Focus the slot
        slot.focus()

        # Press Enter key
        slot.press("Enter")

        # Wait for modal to appear
        modal = self.page.locator("#editSlotModal")
        modal.wait_for(state="visible", timeout=5000)

        assert modal.is_visible(), "Modal should open on Enter key press"

        # Close modal
        close_btn = self.page.locator("#editSlotModal .btn-close")
        close_btn.click()

        # Test Space key as well
        slot.focus()
        slot.press("Space")

        # Modal should reappear
        modal.wait_for(state="visible", timeout=5000)
        assert modal.is_visible(), "Modal should open on Space key press"

    def test_clearing_slot_removes_assignment(self):
        """Test that selecting 'Leave Empty' clears an assignment."""
        self._create_test_roster()

        # Find a filled slot
        filled_slots = self.page.locator(".editable-slot:not(.empty-slot)")
        assert filled_slots.count() > 0, "Test requires at least one filled slot"

        filled_slot = filled_slots.first

        # Click to edit
        filled_slot.click()

        # Wait for modal with member select
        member_select = self.page.locator("#memberSelect")
        member_select.wait_for(state="visible", timeout=5000)

        # Select empty option
        member_select.select_option("")

        # Save
        save_btn = self.page.locator("#saveSlotBtn")
        save_btn.click()

        # Wait for modal to close
        modal = self.page.locator("#editSlotModal")
        modal.wait_for(state="hidden", timeout=5000)

        # Verify cell is now empty
        cell_classes = filled_slot.get_attribute("class") or ""
        assert "empty-slot" in cell_classes, "Cell should be marked as empty"

        # Verify content is em dash
        cell_text = filled_slot.locator(".slot-content").text_content() or ""
        assert "—" in cell_text, "Cell should show empty placeholder"
