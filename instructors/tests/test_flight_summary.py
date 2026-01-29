"""
Tests for get_flight_summary_for_member function.

Issue #559: Flying Summary had incorrect instruction tallies where
solo + with_instructor could exceed total flights due to a bug in
how default values were applied using the totals accumulator.
"""

import pytest
from django.test import TestCase

from instructors.utils import get_flight_summary_for_member
from logsheet.models import Airfield, Flight, Glider, Logsheet, Towplane
from members.models import Member


@pytest.mark.django_db
class TestGetFlightSummaryForMember(TestCase):
    """Tests for the get_flight_summary_for_member utility function."""

    @classmethod
    def setUpTestData(cls):
        """Create test data for flight summary tests."""
        # Create a test member (pilot)
        cls.pilot = Member.objects.create(
            username="test_pilot",
            first_name="Test",
            last_name="Pilot",
            email="pilot@example.com",
            membership_status="Full Member",
        )

        # Create an instructor
        cls.instructor = Member.objects.create(
            username="test_instructor",
            first_name="Test",
            last_name="Instructor",
            email="instructor@example.com",
            membership_status="Full Member",
            instructor=True,
        )

        # Create test gliders
        cls.glider1 = Glider.objects.create(
            n_number="N11111",
            make="Test",
            model="Glider1",
            club_owned=True,
            is_active=True,
        )
        cls.glider2 = Glider.objects.create(
            n_number="N22222",
            make="Test",
            model="Glider2",
            club_owned=True,
            is_active=True,
        )

        # Create a towplane
        cls.towplane = Towplane.objects.create(
            n_number="N99999",
            make="Test",
            model="Tow",
            club_owned=True,
            is_active=True,
        )

        # Create an airfield
        cls.airfield = Airfield.objects.create(name="Test Field", identifier="KXYZ")

        # Create a logsheet
        cls.logsheet = Logsheet.objects.create(
            log_date="2025-01-01",
            airfield=cls.airfield,
            created_by=cls.pilot,
            finalized=True,
        )

        # Create flights with different combinations:
        # Glider1: 3 solo flights
        for _ in range(3):
            Flight.objects.create(
                logsheet=cls.logsheet,
                pilot=cls.pilot,
                glider=cls.glider1,
                towplane=cls.towplane,
                instructor=None,  # Solo
            )

        # Glider1: 2 flights with instructor
        for _ in range(2):
            Flight.objects.create(
                logsheet=cls.logsheet,
                pilot=cls.pilot,
                glider=cls.glider1,
                towplane=cls.towplane,
                instructor=cls.instructor,
            )

        # Glider2: 4 solo flights (no instructor flights at all)
        # This is the key test case for Issue #559 - glider with only solo
        # flights was getting incorrect with_count due to the totals accumulator bug
        for _ in range(4):
            Flight.objects.create(
                logsheet=cls.logsheet,
                pilot=cls.pilot,
                glider=cls.glider2,
                towplane=cls.towplane,
                instructor=None,  # Solo only
            )

    def test_solo_plus_with_equals_total(self):
        """
        Verify that solo_count + with_count == total_count for each glider.

        This tests the fix for Issue #559 where the totals accumulator was
        being used to set defaults, causing with_count to be incorrectly
        set to the accumulated value instead of 0.
        """
        summary = get_flight_summary_for_member(self.pilot)

        for row in summary:
            solo = row.get("solo_count", 0)
            with_instructor = row.get("with_count", 0)
            total = row.get("total_count", 0)

            assert solo + with_instructor == total, (
                f"Glider {row['n_number']}: solo({solo}) + with({with_instructor}) "
                f"!= total({total})"
            )

    def test_glider_with_only_solo_flights_has_zero_with_count(self):
        """
        Glider2 has only solo flights, so with_count should be 0.

        This is the specific regression test for Issue #559.
        """
        summary = get_flight_summary_for_member(self.pilot)

        # Find the row for glider2
        glider2_row = next(
            (r for r in summary if r["n_number"] == self.glider2.n_number), None
        )
        assert glider2_row is not None, "Glider2 should appear in summary"

        assert glider2_row["solo_count"] == 4, "Should have 4 solo flights"
        assert glider2_row["with_count"] == 0, "Should have 0 flights with instructor"
        assert glider2_row["total_count"] == 4, "Should have 4 total flights"

    def test_glider_with_mixed_flights(self):
        """Glider1 has both solo and instructor flights."""
        summary = get_flight_summary_for_member(self.pilot)

        glider1_row = next(
            (r for r in summary if r["n_number"] == self.glider1.n_number), None
        )
        assert glider1_row is not None, "Glider1 should appear in summary"

        assert glider1_row["solo_count"] == 3, "Should have 3 solo flights"
        assert glider1_row["with_count"] == 2, "Should have 2 flights with instructor"
        assert glider1_row["total_count"] == 5, "Should have 5 total flights"

    def test_totals_row_is_correct(self):
        """The Totals row should correctly sum all gliders."""
        summary = get_flight_summary_for_member(self.pilot)

        totals_row = next((r for r in summary if r["n_number"] == "Totals"), None)
        assert totals_row is not None, "Totals row should exist"

        # Glider1: 3 solo + 2 with = 5 total
        # Glider2: 4 solo + 0 with = 4 total
        # Total: 7 solo + 2 with = 9 total
        assert totals_row["solo_count"] == 7, "Total solo should be 7"
        assert totals_row["with_count"] == 2, "Total with instructor should be 2"
        assert totals_row["total_count"] == 9, "Total flights should be 9"

    def test_with_count_never_exceeds_total(self):
        """with_count should never be greater than total_count."""
        summary = get_flight_summary_for_member(self.pilot)

        for row in summary:
            with_instructor = row.get("with_count", 0)
            total = row.get("total_count", 0)

            assert with_instructor <= total, (
                f"Glider {row['n_number']}: with_count({with_instructor}) > "
                f"total_count({total})"
            )
