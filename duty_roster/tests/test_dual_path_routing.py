"""
Tests for dual-path scheduler routing (OR-Tools vs legacy).

Tests the feature flag logic that routes roster generation to either
OR-Tools constraint programming scheduler or legacy weighted-random algorithm.
"""

from datetime import date
from unittest.mock import patch

from django.test import TestCase

from duty_roster.roster_generator import generate_roster
from members.constants.membership import DEFAULT_ROLES
from members.models import Member
from siteconfig.models import SiteConfiguration


class DualPathRoutingTests(TestCase):
    """Test feature flag routing between OR-Tools and legacy schedulers."""

    def setUp(self):
        """Create test members and site configuration."""
        # Create minimal test members
        self.member1 = Member.objects.create(
            username="test_member1",
            first_name="Test",
            last_name="Member1",
            email="test1@example.com",
            membership_status="Full Member",
            is_active=True,
            instructor=True,
            towpilot=True,
            duty_officer=True,
            assistant_duty_officer=True,
        )
        self.member2 = Member.objects.create(
            username="test_member2",
            first_name="Test",
            last_name="Member2",
            email="test2@example.com",
            membership_status="Full Member",
            is_active=True,
            instructor=True,
            towpilot=True,
            duty_officer=True,
            assistant_duty_officer=True,
        )

        # Create site configuration
        self.config = SiteConfiguration.objects.create(
            club_name="Test Club",
            domain_name="test.org",
            club_abbreviation="TC",
            use_ortools_scheduler=False,  # Start with legacy
        )

    def test_routes_to_legacy_when_flag_disabled(self):
        """Test that legacy scheduler is used when feature flag is False."""
        self.config.use_ortools_scheduler = False
        self.config.save()

        with patch(
            "duty_roster.roster_generator._generate_roster_legacy"
        ) as mock_legacy:
            mock_legacy.return_value = []

            generate_roster(year=2026, month=3, roles=DEFAULT_ROLES)

            # Legacy should be called
            mock_legacy.assert_called_once_with(2026, 3, DEFAULT_ROLES, None)

    def test_routes_to_ortools_when_flag_enabled(self):
        """Test that OR-Tools scheduler is used when feature flag is True."""
        self.config.use_ortools_scheduler = True
        self.config.save()

        with patch(
            "duty_roster.ortools_scheduler.generate_roster_ortools"
        ) as mock_ortools:
            mock_ortools.return_value = []

            generate_roster(year=2026, month=3, roles=DEFAULT_ROLES)

            # OR-Tools should be called
            mock_ortools.assert_called_once_with(2026, 3, DEFAULT_ROLES, None)

    def test_fallback_to_legacy_when_ortools_fails(self):
        """Test that legacy scheduler is used if OR-Tools raises exception."""
        self.config.use_ortools_scheduler = True
        self.config.save()

        with patch(
            "duty_roster.ortools_scheduler.generate_roster_ortools"
        ) as mock_ortools, patch(
            "duty_roster.roster_generator._generate_roster_legacy"
        ) as mock_legacy:

            # Make OR-Tools raise an exception
            mock_ortools.side_effect = RuntimeError("Solver failed")
            mock_legacy.return_value = []

            generate_roster(year=2026, month=3, roles=DEFAULT_ROLES)

            # OR-Tools should be attempted
            mock_ortools.assert_called_once()

            # Legacy should be called as fallback
            mock_legacy.assert_called_once_with(2026, 3, DEFAULT_ROLES, None)

    def test_uses_legacy_when_no_config_exists(self):
        """Test that legacy scheduler is used if SiteConfiguration doesn't exist."""
        # Delete config
        SiteConfiguration.objects.all().delete()

        with patch(
            "duty_roster.roster_generator._generate_roster_legacy"
        ) as mock_legacy:
            mock_legacy.return_value = []

            generate_roster(year=2026, month=3, roles=DEFAULT_ROLES)

            # Legacy should be called
            mock_legacy.assert_called_once_with(2026, 3, DEFAULT_ROLES, None)

    def test_passes_all_parameters_to_legacy(self):
        """Test that all parameters are correctly passed to legacy scheduler."""
        self.config.use_ortools_scheduler = False
        self.config.save()

        roles = ["Instructor", "Tow Pilot"]
        exclude = {date(2026, 3, 15), date(2026, 3, 16)}

        with patch(
            "duty_roster.roster_generator._generate_roster_legacy"
        ) as mock_legacy:
            mock_legacy.return_value = []

            generate_roster(year=2026, month=3, roles=roles, exclude_dates=exclude)

            # Verify all parameters passed correctly
            mock_legacy.assert_called_once_with(2026, 3, roles, exclude)

    def test_passes_all_parameters_to_ortools(self):
        """Test that all parameters are correctly passed to OR-Tools scheduler."""
        self.config.use_ortools_scheduler = True
        self.config.save()

        roles = ["Instructor", "Tow Pilot"]
        exclude = {date(2026, 3, 15), date(2026, 3, 16)}

        with patch(
            "duty_roster.ortools_scheduler.generate_roster_ortools"
        ) as mock_ortools:
            mock_ortools.return_value = []

            generate_roster(year=2026, month=3, roles=roles, exclude_dates=exclude)

            # Verify all parameters passed correctly
            mock_ortools.assert_called_once_with(2026, 3, roles, exclude)

    def test_returns_schedule_from_legacy(self):
        """Test that schedule returned by legacy scheduler is passed through."""
        self.config.use_ortools_scheduler = False
        self.config.save()

        expected_schedule = [{"date": date(2026, 3, 1), "slots": {}, "diagnostics": {}}]

        with patch(
            "duty_roster.roster_generator._generate_roster_legacy"
        ) as mock_legacy:
            mock_legacy.return_value = expected_schedule

            result = generate_roster(year=2026, month=3)

            self.assertEqual(result, expected_schedule)

    def test_returns_schedule_from_ortools(self):
        """Test that schedule returned by OR-Tools scheduler is passed through."""
        self.config.use_ortools_scheduler = True
        self.config.save()

        expected_schedule = [{"date": date(2026, 3, 1), "slots": {}, "diagnostics": {}}]

        with patch(
            "duty_roster.ortools_scheduler.generate_roster_ortools"
        ) as mock_ortools:
            mock_ortools.return_value = expected_schedule

            result = generate_roster(year=2026, month=3)

            self.assertEqual(result, expected_schedule)
