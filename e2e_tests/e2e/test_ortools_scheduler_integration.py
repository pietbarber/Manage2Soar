"""
E2E tests for OR-Tools scheduler feature flag integration.

Issue #642: Verify that roster generation works correctly with both
legacy and OR-Tools schedulers, and that the feature flag seamlessly
switches between them without breaking the UI.
"""

from duty_roster.models import DutyPreference
from siteconfig.models import SiteConfiguration

from .conftest import DjangoPlaywrightTestCase


class TestORToolsSchedulerIntegration(DjangoPlaywrightTestCase):
    """Test roster generation UI with OR-Tools and legacy schedulers."""

    def setUp(self):
        """Set up test data for roster generation tests."""
        super().setUp()

        # Create site configuration with scheduling enabled
        self.config = SiteConfiguration.objects.create(
            club_name="Test Club",
            domain_name="test.org",
            club_abbreviation="TC",
            schedule_instructors=True,
            schedule_tow_pilots=True,
            schedule_duty_officers=True,
            schedule_assistant_duty_officers=True,
            use_ortools_scheduler=False,  # Start with legacy
            operations_start_period="First weekend of March",
            operations_end_period="Last weekend of November",
        )

        # Create rostermeister with permissions
        self.rostermeister = self.create_test_member(
            username="rostermeister",
            email="roster@example.com",
            instructor=True,
            towpilot=True,
            duty_officer=True,
            assistant_duty_officer=True,
            is_superuser=False,
            rostermeister=True,
        )
        from django.contrib.auth.models import Group

        rostermeister_group, _ = Group.objects.get_or_create(name="rostermeister")
        self.rostermeister.groups.add(rostermeister_group)

        # Create sufficient members for realistic roster (10 members)
        self.members = []
        for i in range(1, 11):
            member = self.create_test_member(
                username=f"pilot{i}",
                email=f"pilot{i}@example.com",
                instructor=(i % 2 == 0),
                towpilot=(i % 3 == 0),
                duty_officer=(i % 4 == 0),
                assistant_duty_officer=(i % 5 == 0),
            )
            self.members.append(member)

            # Create duty preferences for each member
            DutyPreference.objects.create(
                member=member,
                dont_schedule=False,
                max_assignments_per_month=4,
                instructor_percent=80 if member.instructor else 0,
                duty_officer_percent=80 if member.duty_officer else 0,
                ado_percent=80 if member.assistant_duty_officer else 0,
                towpilot_percent=80 if member.towpilot else 0,
            )

    def test_roster_generation_with_legacy_scheduler(self):
        """Test that roster generation works with legacy scheduler (flag disabled)."""
        # Ensure legacy scheduler is active
        self.config.use_ortools_scheduler = False
        self.config.save()

        # Login as rostermeister
        self.login(username="rostermeister")

        # Navigate to propose roster page
        test_year = 2026
        test_month = 6
        self.page.goto(
            f"{self.live_server_url}/duty_roster/propose-roster/?year={test_year}&month={test_month}"
        )

        # Wait for page to load
        self.page.wait_for_selector("h2", timeout=10000)
        assert "Propose Duty Roster" in self.page.content()

        # Click roll button to generate roster
        roll_button = self.page.locator('button[name="action"][value="roll"]')
        assert roll_button.count() > 0, "Roll button should be present"
        roll_button.click()

        # Wait for roster to be generated and page to reload
        self.page.wait_for_load_state("networkidle", timeout=15000)

        # Verify roster was generated (should have filled slots)
        filled_slots = self.page.locator(".roster-slot:not(.empty-slot)")
        assert filled_slots.count() > 0, "Roster should have filled slots"

        # Verify no error messages
        error_messages = self.page.locator(".alert-danger")
        assert error_messages.count() == 0, "Should not have error messages"

    def test_roster_generation_with_ortools_scheduler(self):
        """Test that roster generation works with OR-Tools scheduler (flag enabled)."""
        # Enable OR-Tools scheduler
        self.config.use_ortools_scheduler = True
        self.config.save()

        # Login as rostermeister
        self.login(username="rostermeister")

        # Navigate to propose roster page
        test_year = 2026
        test_month = 6
        self.page.goto(
            f"{self.live_server_url}/duty_roster/propose-roster/?year={test_year}&month={test_month}"
        )

        # Wait for page to load
        self.page.wait_for_selector("h2", timeout=10000)
        assert "Propose Duty Roster" in self.page.content()

        # Click roll button to generate roster
        roll_button = self.page.locator('button[name="action"][value="roll"]')
        assert roll_button.count() > 0, "Roll button should be present"
        roll_button.click()

        # Wait for roster to be generated and page to reload
        self.page.wait_for_load_state("networkidle", timeout=15000)

        # Verify roster was generated (should have filled slots)
        filled_slots = self.page.locator(".roster-slot:not(.empty-slot)")
        assert filled_slots.count() > 0, "Roster should have filled slots"

        # Verify no error messages
        error_messages = self.page.locator(".alert-danger")
        assert error_messages.count() == 0, "Should not have error messages"

    def test_switching_between_schedulers(self):
        """Test that switching feature flag doesn't break roster generation."""
        # Login as rostermeister
        self.login(username="rostermeister")

        test_year = 2026
        test_month = 6

        # Generate roster with legacy scheduler
        self.config.use_ortools_scheduler = False
        self.config.save()

        self.page.goto(
            f"{self.live_server_url}/duty_roster/propose-roster/?year={test_year}&month={test_month}"
        )
        self.page.wait_for_selector("h2", timeout=10000)

        roll_button = self.page.locator('button[name="action"][value="roll"]')
        if roll_button.count() > 0:
            roll_button.click()
            self.page.wait_for_load_state("networkidle", timeout=15000)

        legacy_filled_count = self.page.locator(".roster-slot:not(.empty-slot)").count()
        assert legacy_filled_count > 0, "Legacy scheduler should fill slots"

        # Switch to OR-Tools scheduler
        self.config.use_ortools_scheduler = True
        self.config.save()

        # Generate roster again with OR-Tools
        self.page.goto(
            f"{self.live_server_url}/duty_roster/propose-roster/?year={test_year}&month={test_month}"
        )
        self.page.wait_for_selector("h2", timeout=10000)

        roll_button = self.page.locator('button[name="action"][value="roll"]')
        if roll_button.count() > 0:
            roll_button.click()
            self.page.wait_for_load_state("networkidle", timeout=15000)

        ortools_filled_count = self.page.locator(
            ".roster-slot:not(.empty-slot)"
        ).count()
        assert ortools_filled_count > 0, "OR-Tools scheduler should fill slots"

        # Both schedulers should produce similar results (both should fill the roster)
        # Allow some variation since schedulers use different algorithms
        assert (
            abs(legacy_filled_count - ortools_filled_count) <= 5
        ), "Both schedulers should produce similar fill rates"

    def test_roster_roll_again_with_ortools(self):
        """Test that 'Roll Again' functionality works with OR-Tools scheduler."""
        # Enable OR-Tools scheduler
        self.config.use_ortools_scheduler = True
        self.config.save()

        # Login as rostermeister
        self.login(username="rostermeister")

        test_year = 2026
        test_month = 6
        self.page.goto(
            f"{self.live_server_url}/duty_roster/propose-roster/?year={test_year}&month={test_month}"
        )
        self.page.wait_for_selector("h2", timeout=10000)

        # Generate initial roster
        roll_button = self.page.locator('button[name="action"][value="roll"]')
        if roll_button.count() > 0:
            roll_button.click()
            self.page.wait_for_load_state("networkidle", timeout=15000)

        first_filled_count = self.page.locator(".roster-slot:not(.empty-slot)").count()
        assert first_filled_count > 0, "Initial roster should have filled slots"

        # Click "Roll Again" button
        roll_again_button = self.page.locator('button[name="action"][value="roll"]')
        assert roll_again_button.count() > 0, "Roll Again button should be present"
        roll_again_button.click()
        self.page.wait_for_load_state("networkidle", timeout=15000)

        second_filled_count = self.page.locator(".roster-slot:not(.empty-slot)").count()
        assert second_filled_count > 0, "Re-rolled roster should have filled slots"

        # Verify no error messages
        error_messages = self.page.locator(".alert-danger")
        assert (
            error_messages.count() == 0
        ), "Should not have error messages after re-roll"

    def test_roster_publish_with_ortools(self):
        """Test that publishing roster works with OR-Tools scheduler."""
        # Enable OR-Tools scheduler
        self.config.use_ortools_scheduler = True
        self.config.save()

        # Login as rostermeister
        self.login(username="rostermeister")

        test_year = 2026
        test_month = 6
        self.page.goto(
            f"{self.live_server_url}/duty_roster/propose-roster/?year={test_year}&month={test_month}"
        )
        self.page.wait_for_selector("h2", timeout=10000)

        # Generate roster
        roll_button = self.page.locator('button[name="action"][value="roll"]')
        if roll_button.count() > 0:
            roll_button.click()
            self.page.wait_for_load_state("networkidle", timeout=15000)

        # Verify roster has filled slots
        filled_slots = self.page.locator(".roster-slot:not(.empty-slot)")
        assert (
            filled_slots.count() > 0
        ), "Roster should have filled slots before publish"

        # Click publish button
        publish_button = self.page.locator('button[name="action"][value="publish"]')
        if publish_button.count() > 0:
            publish_button.click()
            self.page.wait_for_load_state("networkidle", timeout=15000)

            # Should redirect to view roster page and show success message
            # (or stay on propose page if validation failed)
            # Either way, no error messages should appear
            error_messages = self.page.locator(".alert-danger")
            assert (
                error_messages.count() == 0
            ), "Should not have error messages after publish"
