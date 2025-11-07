"""
Tests for operational calendar functionality.
"""

import pytest
from datetime import date
from django.test import TestCase
from django.core.exceptions import ValidationError

from duty_roster.operational_calendar import (
    parse_operational_period,
    get_operational_weekend,
    find_weekend_for_week
)
from duty_roster.roster_generator import is_within_operational_season, clear_operational_season_cache
from siteconfig.models import SiteConfiguration


class TestOperationalCalendar(TestCase):
    """Test operational calendar parsing and weekend calculations."""

    def test_parse_operational_period_basic_formats(self):
        """Test parsing of basic operational period formats."""
        # Test word forms
        self.assertEqual(parse_operational_period("First weekend of May"), (1, 5))
        self.assertEqual(parse_operational_period(
            "Second weekend of December"), (2, 12))
        self.assertEqual(parse_operational_period("Last weekend of October"), (-1, 10))

        # Test numeric forms
        self.assertEqual(parse_operational_period("1st weekend of May"), (1, 5))
        self.assertEqual(parse_operational_period("2nd weekend of Dec"), (2, 12))

        # Test case insensitivity
        self.assertEqual(parse_operational_period("FIRST WEEKEND OF MAY"), (1, 5))
        self.assertEqual(parse_operational_period("third weekend of april"), (3, 4))

        # Test connecting words
        self.assertEqual(parse_operational_period("First weekend in May"), (1, 5))
        self.assertEqual(parse_operational_period("Second weekend May"), (2, 5))

    def test_parse_operational_period_abbreviations(self):
        """Test parsing with month abbreviations."""
        self.assertEqual(parse_operational_period("First weekend of Jan"), (1, 1))
        self.assertEqual(parse_operational_period("1st weekend of Sep"), (1, 9))
        self.assertEqual(parse_operational_period("Last weekend Oct"), (-1, 10))

    def test_parse_operational_period_errors(self):
        """Test error handling in parsing."""
        with self.assertRaises(ValueError):
            parse_operational_period("First day of May")  # No "weekend"

        with self.assertRaises(ValueError):
            parse_operational_period("Fifth weekend of May")  # Invalid ordinal

        with self.assertRaises(ValueError):
            parse_operational_period("First weekend of Invalid")  # Invalid month

    def test_get_operational_weekend_edge_cases(self):
        """Test weekend calculation for edge cases."""
        # May 2022: May 1st is a Sunday
        # First weekend should include Saturday April 30th
        sat, sun = get_operational_weekend(2022, "First weekend of May")
        self.assertEqual(sat, date(2022, 4, 30))
        self.assertEqual(sun, date(2022, 5, 1))

        # May 2021: May 1st is a Saturday
        # First weekend should be May 1-2
        sat, sun = get_operational_weekend(2021, "First weekend of May")
        self.assertEqual(sat, date(2021, 5, 1))
        self.assertEqual(sun, date(2021, 5, 2))

    def test_get_operational_weekend_last_weekend(self):
        """Test last weekend calculation."""
        # October 2021: October 31st is a Sunday
        # Last weekend should be October 30-31
        sat, sun = get_operational_weekend(2021, "Last weekend of October")
        self.assertEqual(sat, date(2021, 10, 30))
        self.assertEqual(sun, date(2021, 10, 31))


class TestOperationalSeason(TestCase):
    """Test operational season filtering logic."""

    def setUp(self):
        """Create test configuration."""
        clear_operational_season_cache()  # Clear cache between tests
        self.config = SiteConfiguration.objects.create(
            club_name="Test Club",
            domain_name="test.example.com",
            club_abbreviation="TC",
            operations_start_period="First weekend of May",
            operations_end_period="Last weekend of October"
        )

    def test_is_within_operational_season_both_configured(self):
        """Test season filtering when both start and end are configured."""
        # Date within season (summer)
        self.assertTrue(is_within_operational_season(date(2023, 7, 15)))

        # Date before season (winter)
        self.assertFalse(is_within_operational_season(date(2023, 2, 15)))

        # Date after season (winter)
        self.assertFalse(is_within_operational_season(date(2023, 12, 15)))

        # Edge cases - exact start/end dates
        self.assertTrue(is_within_operational_season(
            date(2023, 5, 6)))  # First Saturday of May
        self.assertTrue(is_within_operational_season(
            date(2023, 10, 28)))  # Last Saturday of October

    def test_is_within_operational_season_only_start(self):
        """Test season filtering when only start period is configured."""
        self.config.operations_end_period = ""
        self.config.save()
        clear_operational_season_cache()  # Clear cache after config change

        # Date after start should be allowed
        self.assertTrue(is_within_operational_season(date(2023, 7, 15)))
        self.assertTrue(is_within_operational_season(date(2023, 12, 15)))

        # Date before start should be blocked
        self.assertFalse(is_within_operational_season(date(2023, 2, 15)))

    def test_is_within_operational_season_only_end(self):
        """Test season filtering when only end period is configured."""
        self.config.operations_start_period = ""
        self.config.save()
        clear_operational_season_cache()  # Clear cache after config change

        # Date before end should be allowed
        self.assertTrue(is_within_operational_season(date(2023, 7, 15)))
        self.assertTrue(is_within_operational_season(date(2023, 2, 15)))

        # Date after end should be blocked
        self.assertFalse(is_within_operational_season(date(2023, 12, 15)))

    def test_is_within_operational_season_no_config(self):
        """Test season filtering when no periods are configured."""
        self.config.operations_start_period = ""
        self.config.operations_end_period = ""
        self.config.save()
        clear_operational_season_cache()  # Clear cache after config change

        # All dates should be allowed
        self.assertTrue(is_within_operational_season(date(2023, 1, 15)))
        self.assertTrue(is_within_operational_season(date(2023, 7, 15)))
        self.assertTrue(is_within_operational_season(date(2023, 12, 15)))

    def test_is_within_operational_season_no_siteconfig(self):
        """Test season filtering when no SiteConfiguration exists."""
        SiteConfiguration.objects.all().delete()
        clear_operational_season_cache()  # Clear cache after deletion

        # All dates should be allowed
        self.assertTrue(is_within_operational_season(date(2023, 1, 15)))
        self.assertTrue(is_within_operational_season(date(2023, 7, 15)))
        self.assertTrue(is_within_operational_season(date(2023, 12, 15)))


class TestSiteConfigValidation(TestCase):
    """Test SiteConfiguration validation for operational periods."""

    def test_valid_operational_periods(self):
        """Test that valid operational periods pass validation."""
        config = SiteConfiguration(
            club_name="Test Club",
            domain_name="test.example.com",
            club_abbreviation="TC",
            operations_start_period="First weekend of May",
            operations_end_period="Last weekend of October"
        )
        # Should not raise ValidationError
        config.full_clean()

    def test_invalid_operational_period_format(self):
        """Test that invalid operational periods fail validation."""
        config = SiteConfiguration(
            club_name="Test Club",
            domain_name="test.example.com",
            club_abbreviation="TC",
            operations_start_period="Invalid format",
            operations_end_period="Last weekend of October"
        )

        with self.assertRaises(ValidationError) as cm:
            config.full_clean()

        self.assertIn('operations_start_period', cm.exception.message_dict)

    def test_empty_operational_periods_allowed(self):
        """Test that empty operational periods are allowed."""
        config = SiteConfiguration(
            club_name="Test Club",
            domain_name="test.example.com",
            club_abbreviation="TC",
            operations_start_period="",
            operations_end_period=""
        )
        # Should not raise ValidationError
        config.full_clean()
