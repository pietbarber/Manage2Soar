"""
E2E tests for roster slot editing and diagnostics.

Issue #616: Verify JavaScript correctly handles clicking roster slots,
loading eligible members via AJAX, saving assignments, and displaying diagnostics.
"""

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

        # Create 4 schedulable members to avoid hitting max assignments after roster generation
        self.member1 = self.create_test_member(
            username="pilot1",
            email="pilot1@example.com",
            instructor=True,
            towpilot=True,
            assistant_duty_officer=True,
        )
        self.member2 = self.create_test_member(
            username="pilot2",
            email="pilot2@example.com",
            instructor=True,
            towpilot=True,
            assistant_duty_officer=True,
        )
        self.member3 = self.create_test_member(
            username="pilot3",
            email="pilot3@example.com",
            instructor=True,
            towpilot=True,
            duty_officer=True,
            assistant_duty_officer=True,
        )
        self.member4 = self.create_test_member(
            username="pilot4",
            email="pilot4@example.com",
            instructor=True,
            towpilot=True,
            duty_officer=True,
            assistant_duty_officer=True,
        )

        # Create duty preferences for members (100% for all roles to ensure eligibility)
        # Use max 6 assignments to ensure there are always some empty slots for testing
        DutyPreference.objects.create(
            member=self.member1,
            dont_schedule=False,
            max_assignments_per_month=6,
            instructor_percent=100,
            duty_officer_percent=100,
            ado_percent=100,
            towpilot_percent=100,
        )
        DutyPreference.objects.create(
            member=self.member2,
            dont_schedule=False,
            max_assignments_per_month=6,
            instructor_percent=100,
            duty_officer_percent=100,
            ado_percent=100,
            towpilot_percent=100,
        )
        DutyPreference.objects.create(
            member=self.member3,
            dont_schedule=False,
            max_assignments_per_month=6,
            instructor_percent=100,
            duty_officer_percent=100,
            ado_percent=100,
            towpilot_percent=100,
        )
        DutyPreference.objects.create(
            member=self.member4,
            dont_schedule=False,
            max_assignments_per_month=6,
            instructor_percent=100,
            duty_officer_percent=100,
            ado_percent=100,
            towpilot_percent=100,
        )

    def _create_test_roster(self):
        """Helper to create a test roster and navigate to propose page."""
        # Login as rostermeister
        self.login(username="rostermeister")

        # Use a fixed month/year to avoid time-dependent test behavior
        test_year = 2024
        test_month = 6
        self.page.goto(
            f"{self.live_server_url}/duty_roster/propose-roster/?year={test_year}&month={test_month}"
        )

        # Wait for page to load
        self.page.wait_for_selector("h2", timeout=10000)

        # Check if there's a roster to work with, or generate one
        roll_button = self.page.locator('button[name="action"][value="roll"]')
        if roll_button.count() > 0:
            # Click roll button to generate roster
            roll_button.click()

            # Wait for roster to be created and page to reload
            self.page.wait_for_load_state("networkidle", timeout=15000)

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

        # Find a FILLED slot to edit (avoids the choice modal flow)
        filled_slots = self.page.locator(".roster-slot.editable-slot:not(.empty-slot)")
        if filled_slots.count() == 0:
            # If no filled slots, use empty slot
            filled_slots = self.page.locator(".empty-slot.editable-slot")

        assert filled_slots.count() > 0, "Test requires at least one slot"

        test_slot = filled_slots.first

        # Get slot attributes BEFORE clicking to avoid stale values after AJAX update
        slot_role = test_slot.get_attribute("data-role")
        slot_date = test_slot.get_attribute("data-date")

        # Click slot to open edit modal
        test_slot.click()

        # Wait for edit modal
        modal = self.page.locator("#editSlotModal")
        modal.wait_for(state="visible", timeout=5000)

        # If it's the choice modal, click assign to get to edit modal
        assign_btn = self.page.locator("#assignSlotFromChoiceBtn")
        if assign_btn.is_visible():
            assign_btn.click()
            self.page.wait_for_timeout(500)

        # Wait for member select
        member_select = self.page.locator("#memberSelect")
        member_select.wait_for(state="visible", timeout=5000)

        # Select a different member (not the first, since slot may already have first member)
        options = member_select.locator('option:not([value=""])')
        assert options.count() > 0, "Test requires at least one eligible member"

        # Select the last option to ensure it's different from current
        option_to_select = options.last
        member_value = option_to_select.get_attribute("value")
        member_name = option_to_select.text_content() or ""
        member_name_only = member_name.split("[")[0].strip()

        member_select.select_option(member_value)

        # Click save
        save_btn = self.page.locator("#saveSlotBtn")
        save_btn.click()

        # Wait for modal to close and DOM to update
        modal.wait_for(state="hidden", timeout=5000)

        # Wait for DOM update to complete - network idle ensures AJAX has finished
        self.page.wait_for_load_state("networkidle", timeout=5000)

        # Re-query the slot using the attributes we saved before clicking
        updated_slot = self.page.locator(
            f".roster-slot[data-role='{slot_role}'][data-date='{slot_date}']"
        )
        updated_content = updated_slot.text_content() or ""

        # Verify the member name appears in the slot
        assert (
            member_name_only in updated_content
        ), f"Cell should contain selected member name '{member_name_only}', but got: {updated_content}"

        # Verify cell doesn't have empty-slot class
        cell_classes = updated_slot.get_attribute("class") or ""
        assert "empty-slot" not in cell_classes, "Cell should not be marked as empty"

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

        # Get slot attributes before clicking to re-query later
        slot_role = filled_slot.get_attribute("data-role")
        slot_date = filled_slot.get_attribute("data-date")

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

        # Wait for DOM update - network idle ensures AJAX has finished
        self.page.wait_for_load_state("networkidle", timeout=5000)

        # Re-query the slot to get fresh attributes
        updated_slot = self.page.locator(
            f".roster-slot[data-role='{slot_role}'][data-date='{slot_date}']"
        )

        # Verify cell is now empty
        cell_classes = updated_slot.get_attribute("class") or ""
        assert "empty-slot" in cell_classes, "Cell should be marked as empty"

        # Verify content is em dash
        cell_text = updated_slot.locator(".slot-content").text_content() or ""
        assert "—" in cell_text, "Cell should show empty placeholder"
