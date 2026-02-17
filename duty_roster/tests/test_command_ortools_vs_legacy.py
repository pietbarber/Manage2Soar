"""
Tests for test_ortools_vs_legacy management command.

Tests the side-by-side scheduler comparison functionality.
"""

import json
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from members.models import Member
from siteconfig.models import SiteConfiguration


class TestORToolsVsLegacyCommandTests(TestCase):
    """Test test_ortools_vs_legacy management command."""

    def setUp(self):
        """Create test members and configuration."""
        # Create site configuration with operational season
        self.config = SiteConfiguration.objects.create(
            club_name="Test Club",
            domain_name="test.org",
            club_abbreviation="TC",
            # Set operational season to cover March 2026
            operations_start_period="First weekend of March",
            operations_end_period="Last weekend of November",
        )

        # Create test members with roles
        for i in range(10):
            Member.objects.create(
                username=f"test_member_{i}",
                first_name=f"Test{i}",
                last_name=f"Member{i}",
                email=f"test{i}@example.com",
                membership_status="Full Member",
                is_active=True,
                instructor=(i % 2 == 0),
                towpilot=(i % 3 == 0),
                duty_officer=(i % 4 == 0),
                assistant_duty_officer=(i % 5 == 0),
            )

    def test_command_runs_successfully(self):
        """Test that command runs without errors."""
        out = StringIO()
        call_command("test_ortools_vs_legacy", "--year=2026", "--month=3", stdout=out)

        output = out.getvalue()
        self.assertIn("Scheduler Comparison Report", output)
        self.assertIn("LEGACY SCHEDULER:", output)
        self.assertIn("OR-TOOLS SCHEDULER:", output)

    def test_command_with_custom_roles(self):
        """Test command with custom role list."""
        out = StringIO()
        call_command(
            "test_ortools_vs_legacy",
            "--year=2026",
            "--month=3",
            "--roles=instructor,towpilot",
            stdout=out,
        )

        output = out.getvalue()
        self.assertIn("Roles: instructor, towpilot", output)

    def test_command_json_output(self):
        """Test that JSON output is valid and contains expected fields."""
        out = StringIO()
        call_command(
            "test_ortools_vs_legacy", "--year=2026", "--month=3", "--json", stdout=out
        )

        # Extract JSON from output (skip the "Comparing..." lines)
        output_lines = out.getvalue().split("\n")
        json_start = next(
            i for i, line in enumerate(output_lines) if line.strip().startswith("{")
        )
        json_text = "\n".join(output_lines[json_start:])

        # Parse JSON
        data = json.loads(json_text)

        # Verify structure
        self.assertEqual(data["year"], 2026)
        self.assertEqual(data["month"], 3)
        self.assertIn("roles", data)
        self.assertIn("context", data)
        self.assertIn("legacy", data)
        self.assertIn("ortools", data)
        self.assertIn("comparison", data)

        # Verify context
        self.assertIn("total_members", data["context"])
        self.assertIn("total_slots", data["context"])

        # Verify scheduler results
        self.assertIn("solve_time_ms", data["legacy"])
        self.assertIn("metrics", data["legacy"])
        self.assertIn("solve_time_ms", data["ortools"])
        self.assertIn("metrics", data["ortools"])

        # Verify comparison
        self.assertIn("total_slots", data["comparison"])
        self.assertIn("same_assignments", data["comparison"])
        self.assertIn("different_assignments", data["comparison"])

    def test_command_shows_solve_times(self):
        """Test that command reports solve times for both schedulers."""
        out = StringIO()
        call_command("test_ortools_vs_legacy", "--year=2026", "--month=3", stdout=out)

        output = out.getvalue()
        self.assertIn("Solve time:", output)
        self.assertIn("ms", output)

    def test_command_shows_slot_fill_rates(self):
        """Test that command reports slot fill rates."""
        out = StringIO()
        call_command("test_ortools_vs_legacy", "--year=2026", "--month=3", stdout=out)

        output = out.getvalue()
        self.assertIn("Slot fill:", output)
        self.assertIn("%", output)

    def test_command_shows_fairness_metrics(self):
        """Test that command reports fairness variance."""
        out = StringIO()
        call_command("test_ortools_vs_legacy", "--year=2026", "--month=3", stdout=out)

        output = out.getvalue()
        self.assertIn("Fairness (variance):", output)

    def test_command_shows_differences(self):
        """Test that command reports differences between schedulers."""
        out = StringIO()
        call_command("test_ortools_vs_legacy", "--year=2026", "--month=3", stdout=out)

        output = out.getvalue()
        self.assertIn("DIFFERENCES:", output)
        self.assertIn("Same assignments:", output)

    def test_command_handles_scheduler_failure_gracefully(self):
        """Test that command handles scheduler failures without crashing."""
        # Mock OR-Tools scheduler to raise an exception
        with patch(
            "duty_roster.management.commands.test_ortools_vs_legacy.generate_roster_ortools"
        ) as mock_ortools:
            mock_ortools.side_effect = RuntimeError("Test failure")

            out = StringIO()
            call_command(
                "test_ortools_vs_legacy", "--year=2026", "--month=3", stdout=out
            )

            output = out.getvalue()
            self.assertIn("OR-TOOLS SCHEDULER:", output)
            self.assertIn("FAILED", output)
            self.assertIn("Test failure", output)

    def test_command_defaults_to_current_month(self):
        """Test that command defaults to current year/month when not specified."""
        out = StringIO()
        # Should not raise an error
        call_command("test_ortools_vs_legacy", stdout=out)

        output = out.getvalue()
        self.assertIn("Scheduler Comparison Report", output)

    def test_verbose_output_shows_slot_differences(self):
        """Test that verbose mode shows slot-by-slot differences."""
        out = StringIO()
        call_command(
            "test_ortools_vs_legacy",
            "--year=2026",
            "--month=3",
            "--verbose",
            stdout=out,
        )

        output = out.getvalue()
        # Verbose mode should show more details
        self.assertIn("DIFFERENCES:", output)
