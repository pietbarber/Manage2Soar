"""
Test performance improvements for Issue #298 - Towplane logbook optimization

Verifies that towplane_logbook uses batch queries instead of N+1 queries
for flight data, member names, and maintenance issues.
"""

import time
from datetime import date
from datetime import time as dt_time
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client, TestCase
from django.test.utils import override_settings
from django.urls import reverse

from logsheet.models import (
    Airfield,
    Flight,
    Glider,
    Logsheet,
    MaintenanceIssue,
    Towplane,
    TowplaneCloseout,
)
from members.models import Member

User = get_user_model()


class TowplaneLogbookPerformanceTestCase(TestCase):
    """
    Test performance improvements in towplane_logbook view.

    Before optimization: O(days) queries - each day triggered 2+ queries
    After optimization: O(1) queries - batch load all data upfront
    """

    def setUp(self):
        """Create test data simulating a towplane with years of history."""
        # Create test member (primary tow pilot)
        self.tow_pilot = Member.objects.create_user(
            username="towpilot",
            password="testpass123",
            first_name="Tow",
            last_name="Pilot",
            membership_status="Full Member",
        )

        # Create additional tow pilots
        self.tow_pilots = [self.tow_pilot]
        for i in range(5):
            pilot = Member.objects.create_user(
                username=f"towpilot{i}",
                password="testpass123",
                first_name=f"Tow{i}",
                last_name=f"Pilot{i}",
                membership_status="Full Member",
            )
            self.tow_pilots.append(pilot)

        # Create airfield
        self.airfield = Airfield.objects.create(name="Test Field", identifier="TEST")

        # Create towplane
        self.towplane = Towplane.objects.create(
            name="Test Towplane",
            n_number="N123TP",
            is_active=True,
        )

        # Create glider for flights
        self.glider = Glider.objects.create(
            competition_number="XY",
            make="Test",
            model="Glider",
            n_number="N123XY",
            is_active=True,
        )

        # Create historical data: 100 days of operations
        # This simulates a towplane used over multiple years
        start_date = date(2020, 1, 1)
        for day_offset in range(100):
            log_date = start_date + timedelta(days=day_offset * 3)  # Every 3 days

            # Create logsheet for this day
            logsheet = Logsheet.objects.create(
                log_date=log_date,
                airfield=self.airfield,
                duty_officer=self.tow_pilot,
                created_by=self.tow_pilot,
            )

            # Create towplane closeout
            tach_start = 1000.0 + (day_offset * 1.5)
            TowplaneCloseout.objects.create(
                logsheet=logsheet,
                towplane=self.towplane,
                start_tach=tach_start,
                end_tach=tach_start + 1.5,
                tach_time=1.5,
            )

            # Create flights for this day (3-5 per day)
            num_flights = 3 + (day_offset % 3)
            tow_pilot = self.tow_pilots[day_offset % len(self.tow_pilots)]

            for i in range(num_flights):
                Flight.objects.create(
                    logsheet=logsheet,
                    pilot=self.tow_pilot,
                    glider=self.glider,
                    towplane=self.towplane,
                    tow_pilot=tow_pilot,
                    release_altitude=2000,
                    launch_time=dt_time(9, 0, 0),
                    landing_time=dt_time(10, 30, 0),
                )

            # Add some maintenance issues (every 10th day)
            if day_offset % 10 == 0:
                MaintenanceIssue.objects.create(
                    logsheet=logsheet,
                    towplane=self.towplane,
                    description=f"Routine maintenance check day {day_offset}",
                    report_date=log_date,
                    grounded=False,
                    resolved=True,
                    resolved_date=log_date + timedelta(days=1),
                )

    @override_settings(DEBUG=True)
    def test_towplane_logbook_query_count(self):
        """
        Test that towplane_logbook uses O(1) queries, not O(days).

        Before optimization:
        - 1 query per day for flights (N queries)
        - 1 query per day for maintenance issues (N more queries)
        - Total: 200+ queries for 100 days

        After optimization:
        - 1 query for all closeouts
        - 1 query for all flights
        - 1 query for all member names
        - 1 query for all maintenance issues
        - Total: ~10 queries
        """
        client = Client()
        client.force_login(self.tow_pilot)

        connection.queries_log.clear()

        start_time = time.time()
        response = client.get(
            reverse("logsheet:towplane_logbook", args=[self.towplane.pk])
        )
        end_time = time.time()

        request_time = end_time - start_time
        query_count = len(connection.queries)

        # Assertions
        self.assertEqual(response.status_code, 200)

        # Performance metrics
        print(f"\n=== TOWPLANE LOGBOOK PERFORMANCE ===")
        print(f"Request time: {request_time:.4f} seconds")
        print(f"Database queries: {query_count}")
        print(
            f"Days of data: {TowplaneCloseout.objects.filter(towplane=self.towplane).count()}"
        )
        print(f"Total flights: {Flight.objects.filter(towplane=self.towplane).count()}")
        print(
            f"Maintenance issues: {MaintenanceIssue.objects.filter(towplane=self.towplane).count()}"
        )

        # The key assertion: query count should be constant, not proportional to days
        # With 100 days of data, N+1 would give 200+ queries
        # Optimized should be under 20 queries
        max_expected_queries = 20
        self.assertLess(
            query_count,
            max_expected_queries,
            f"Query count too high ({query_count}). "
            f"Expected < {max_expected_queries} with batch loading. "
            f"This may indicate N+1 query problem.",
        )

        if query_count > max_expected_queries:
            print(
                f"⚠️  HIGH QUERY COUNT: {query_count} queries (target: < {max_expected_queries})"
            )
        else:
            print(f"✅ Query count acceptable: {query_count} queries")

        if request_time > 2.0:
            print(f"⚠️  SLOW RESPONSE: {request_time:.4f}s (target: < 2.0s)")
        else:
            print(f"✅ Response time good: {request_time:.4f}s")

        # Verify response contains expected data
        self.assertIn("daily", response.context)
        self.assertIn("object", response.context)
        self.assertEqual(response.context["object"], self.towplane)

        # Check we have the expected number of days
        daily = response.context["daily"]
        self.assertEqual(len(daily), 100, "Should have 100 days of data")

    @override_settings(DEBUG=True)
    def test_towplane_logbook_data_integrity(self):
        """
        Verify that the optimized view returns correct data.

        This tests that batch loading doesn't lose or corrupt data.
        """
        client = Client()
        client.force_login(self.tow_pilot)

        response = client.get(
            reverse("logsheet:towplane_logbook", args=[self.towplane.pk])
        )
        self.assertEqual(response.status_code, 200)

        daily = response.context["daily"]

        # Check first and last day have correct structure
        first_day = daily[0]
        last_day = daily[-1]

        for day_data in [first_day, last_day]:
            self.assertIn("day", day_data)
            self.assertIn("glider_tows", day_data)
            self.assertIn("day_hours", day_data)
            self.assertIn("cum_hours", day_data)
            self.assertIn("towpilots", day_data)
            self.assertIn("issues", day_data)

            # Tow count should be positive
            self.assertGreater(day_data["glider_tows"], 0)

            # Tow pilots should be a list of names
            self.assertIsInstance(day_data["towpilots"], list)
            self.assertGreater(len(day_data["towpilots"]), 0)

            # All names should be strings, not member IDs
            for name in day_data["towpilots"]:
                self.assertIsInstance(name, str)
                self.assertNotRegex(name, r"^\d+$", "Tow pilot should be name, not ID")

    @override_settings(DEBUG=True)
    def test_query_analysis(self):
        """Analyze specific query patterns to verify optimization."""
        client = Client()
        client.force_login(self.tow_pilot)

        connection.queries_log.clear()

        response = client.get(
            reverse("logsheet:towplane_logbook", args=[self.towplane.pk])
        )

        queries = connection.queries
        query_sqls = [q["sql"] for q in queries]

        print(f"\n=== QUERY ANALYSIS ===")
        print(f"Total queries: {len(queries)}")

        # Count queries by table
        flight_queries = sum(
            1 for sql in query_sqls if "logsheet_flight" in sql.lower()
        )
        closeout_queries = sum(
            1 for sql in query_sqls if "towplanecloseout" in sql.lower()
        )
        member_queries = sum(1 for sql in query_sqls if "members_member" in sql.lower())
        issue_queries = sum(
            1 for sql in query_sqls if "maintenanceissue" in sql.lower()
        )

        print(f"Flight queries: {flight_queries}")
        print(f"Closeout queries: {closeout_queries}")
        print(f"Member queries: {member_queries}")
        print(f"Maintenance issue queries: {issue_queries}")

        # With batch loading:
        # - Should have at most 1-2 flight queries (not 100)
        # - Should have at most 1-2 closeout queries
        # - Should have at most 1-2 member queries
        # - Should have at most 1-2 issue queries
        self.assertLess(flight_queries, 5, "Flight queries should be batched")
        self.assertLess(closeout_queries, 5, "Closeout queries should be batched")
        self.assertLess(member_queries, 5, "Member queries should be batched")
        self.assertLess(issue_queries, 5, "Issue queries should be batched")

        self.assertEqual(response.status_code, 200)


class TowplaneLogbookEdgeCasesTestCase(TestCase):
    """Test edge cases for towplane logbook view."""

    def setUp(self):
        """Create test data for edge case testing."""
        self.member = Member.objects.create_user(
            username="testpilot",
            password="testpass123",
            first_name="Test",
            last_name="Pilot",
            membership_status="Full Member",
        )

        self.airfield = Airfield.objects.create(name="Test Field", identifier="TEST")

        self.towplane = Towplane.objects.create(
            name="Test Towplane",
            n_number="N123TP",
            is_active=True,
        )

        self.glider = Glider.objects.create(
            competition_number="XY",
            make="Test",
            model="Glider",
            n_number="N123XY",
            is_active=True,
        )

    def test_multiple_closeouts_same_day(self):
        """
        Test aggregation when multiple TowplaneCloseout records exist for the same day.

        This covers the real-world scenario where a towplane is used at different
        times of the day with multiple logsheet entries. The view should aggregate
        tach hours correctly.

        Note: Multiple logsheets for the same day require different airfields due
        to the unique constraint on (log_date, airfield_id).
        """
        log_date = date(2024, 6, 15)

        # Create second airfield for afternoon operations
        afternoon_airfield = Airfield.objects.create(
            name="Afternoon Field", identifier="AFT"
        )

        # Create two logsheets for the same day (e.g., morning and afternoon ops)
        morning_logsheet = Logsheet.objects.create(
            log_date=log_date,
            airfield=self.airfield,
            duty_officer=self.member,
            created_by=self.member,
        )
        afternoon_logsheet = Logsheet.objects.create(
            log_date=log_date,
            airfield=afternoon_airfield,  # Different airfield
            duty_officer=self.member,
            created_by=self.member,
        )

        # Create two closeouts for the same day with different tach times
        TowplaneCloseout.objects.create(
            logsheet=morning_logsheet,
            towplane=self.towplane,
            start_tach=1000.0,
            end_tach=1001.5,
            tach_time=1.5,  # Morning session
        )
        TowplaneCloseout.objects.create(
            logsheet=afternoon_logsheet,
            towplane=self.towplane,
            start_tach=1001.5,
            end_tach=1003.0,
            tach_time=1.5,  # Afternoon session
        )

        # Create flights for both logsheets
        Flight.objects.create(
            logsheet=morning_logsheet,
            pilot=self.member,
            glider=self.glider,
            towplane=self.towplane,
            tow_pilot=self.member,
            release_altitude=2000,
            launch_time=dt_time(9, 0, 0),
            landing_time=dt_time(10, 0, 0),
        )
        Flight.objects.create(
            logsheet=afternoon_logsheet,
            pilot=self.member,
            glider=self.glider,
            towplane=self.towplane,
            tow_pilot=self.member,
            release_altitude=2000,
            launch_time=dt_time(14, 0, 0),
            landing_time=dt_time(15, 0, 0),
        )

        client = Client()
        client.force_login(self.member)

        response = client.get(
            reverse("logsheet:towplane_logbook", args=[self.towplane.pk])
        )

        self.assertEqual(response.status_code, 200)

        # Should have only 1 day entry (aggregated)
        daily = response.context["daily"]
        self.assertEqual(len(daily), 1)

        day_data = daily[0]
        self.assertEqual(day_data["day"], log_date)

        # day_hours should be the SUM of both closeouts (1.5 + 1.5 = 3.0)
        self.assertEqual(day_data["day_hours"], 3.0)

        # cum_hours should be the LAST end_tach value (1003.0)
        self.assertEqual(day_data["cum_hours"], 1003.0)

        # glider_tows should count all flights for the day
        self.assertEqual(day_data["glider_tows"], 2)

    def test_guest_towpilot_name(self):
        """
        Test that guest tow pilot names are correctly displayed.

        Guest tow pilots are non-member tow pilots stored as strings.
        """
        log_date = date(2024, 7, 20)

        logsheet = Logsheet.objects.create(
            log_date=log_date,
            airfield=self.airfield,
            duty_officer=self.member,
            created_by=self.member,
        )

        TowplaneCloseout.objects.create(
            logsheet=logsheet,
            towplane=self.towplane,
            start_tach=1000.0,
            end_tach=1001.0,
            tach_time=1.0,
        )

        # Create flight with guest tow pilot (non-member)
        Flight.objects.create(
            logsheet=logsheet,
            pilot=self.member,
            glider=self.glider,
            towplane=self.towplane,
            tow_pilot=None,  # No member tow pilot
            guest_towpilot_name="John Guest Pilot",  # Guest name
            release_altitude=2000,
            launch_time=dt_time(10, 0, 0),
            landing_time=dt_time(11, 0, 0),
        )

        client = Client()
        client.force_login(self.member)

        response = client.get(
            reverse("logsheet:towplane_logbook", args=[self.towplane.pk])
        )

        self.assertEqual(response.status_code, 200)

        daily = response.context["daily"]
        self.assertEqual(len(daily), 1)

        day_data = daily[0]
        # Guest name should appear in towpilots list
        self.assertIn("John Guest Pilot", day_data["towpilots"])

    def test_legacy_towpilot_name(self):
        """
        Test that legacy tow pilot names are correctly displayed.

        Legacy tow pilot names are from historical data imports.
        """
        log_date = date(2024, 8, 10)

        logsheet = Logsheet.objects.create(
            log_date=log_date,
            airfield=self.airfield,
            duty_officer=self.member,
            created_by=self.member,
        )

        TowplaneCloseout.objects.create(
            logsheet=logsheet,
            towplane=self.towplane,
            start_tach=1000.0,
            end_tach=1001.0,
            tach_time=1.0,
        )

        # Create flight with legacy tow pilot name (from data import)
        Flight.objects.create(
            logsheet=logsheet,
            pilot=self.member,
            glider=self.glider,
            towplane=self.towplane,
            tow_pilot=None,
            guest_towpilot_name=None,
            legacy_towpilot_name="Smith, Robert (Legacy)",  # Legacy import name
            release_altitude=2000,
            launch_time=dt_time(10, 0, 0),
            landing_time=dt_time(11, 0, 0),
        )

        client = Client()
        client.force_login(self.member)

        response = client.get(
            reverse("logsheet:towplane_logbook", args=[self.towplane.pk])
        )

        self.assertEqual(response.status_code, 200)

        daily = response.context["daily"]
        self.assertEqual(len(daily), 1)

        day_data = daily[0]
        # Legacy name should appear in towpilots list
        self.assertIn("Smith, Robert (Legacy)", day_data["towpilots"])

    def test_mixed_towpilot_types(self):
        """
        Test that a day with mixed tow pilot types (member, guest, legacy) works correctly.
        """
        log_date = date(2024, 9, 5)

        logsheet = Logsheet.objects.create(
            log_date=log_date,
            airfield=self.airfield,
            duty_officer=self.member,
            created_by=self.member,
        )

        TowplaneCloseout.objects.create(
            logsheet=logsheet,
            towplane=self.towplane,
            start_tach=1000.0,
            end_tach=1002.0,
            tach_time=2.0,
        )

        # Flight with member tow pilot
        Flight.objects.create(
            logsheet=logsheet,
            pilot=self.member,
            glider=self.glider,
            towplane=self.towplane,
            tow_pilot=self.member,
            release_altitude=2000,
            launch_time=dt_time(9, 0, 0),
            landing_time=dt_time(9, 30, 0),
        )

        # Flight with guest tow pilot
        Flight.objects.create(
            logsheet=logsheet,
            pilot=self.member,
            glider=self.glider,
            towplane=self.towplane,
            tow_pilot=None,
            guest_towpilot_name="Guest Tow Pilot",
            release_altitude=2000,
            launch_time=dt_time(10, 0, 0),
            landing_time=dt_time(10, 30, 0),
        )

        # Flight with legacy tow pilot
        Flight.objects.create(
            logsheet=logsheet,
            pilot=self.member,
            glider=self.glider,
            towplane=self.towplane,
            tow_pilot=None,
            guest_towpilot_name=None,
            legacy_towpilot_name="Legacy Tow Pilot",
            release_altitude=2000,
            launch_time=dt_time(11, 0, 0),
            landing_time=dt_time(11, 30, 0),
        )

        client = Client()
        client.force_login(self.member)

        response = client.get(
            reverse("logsheet:towplane_logbook", args=[self.towplane.pk])
        )

        self.assertEqual(response.status_code, 200)

        daily = response.context["daily"]
        self.assertEqual(len(daily), 1)

        day_data = daily[0]

        # Should have 3 flights
        self.assertEqual(day_data["glider_tows"], 3)

        # All three tow pilot names should appear
        towpilots = day_data["towpilots"]
        self.assertEqual(len(towpilots), 3)

        # Check each type of pilot is represented
        # Member pilot should be resolved to name
        self.assertIn("Test Pilot", towpilots)
        self.assertIn("Guest Tow Pilot", towpilots)
        self.assertIn("Legacy Tow Pilot", towpilots)


class TowplaneLogbookMinimalTestCase(TestCase):
    """Test with minimal data to ensure view works correctly."""

    def setUp(self):
        """Create minimal test data."""
        self.member = Member.objects.create_user(
            username="testpilot",
            password="testpass123",
            first_name="Test",
            last_name="Pilot",
            membership_status="Full Member",
        )

        self.airfield = Airfield.objects.create(name="Test Field", identifier="TEST")

        self.towplane = Towplane.objects.create(
            name="Test Towplane",
            n_number="N123TP",
            is_active=True,
        )

    def test_empty_logbook(self):
        """Test towplane logbook with no closeouts."""
        client = Client()
        client.force_login(self.member)

        response = client.get(
            reverse("logsheet:towplane_logbook", args=[self.towplane.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["daily"]), 0)

    def test_single_day_logbook(self):
        """Test towplane logbook with just one day of data."""
        logsheet = Logsheet.objects.create(
            log_date=date.today(),
            airfield=self.airfield,
            duty_officer=self.member,
            created_by=self.member,
        )

        TowplaneCloseout.objects.create(
            logsheet=logsheet,
            towplane=self.towplane,
            start_tach=100.0,
            end_tach=101.5,
            tach_time=1.5,
        )

        client = Client()
        client.force_login(self.member)

        response = client.get(
            reverse("logsheet:towplane_logbook", args=[self.towplane.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["daily"]), 1)

        day_data = response.context["daily"][0]
        self.assertEqual(day_data["day"], date.today())
        self.assertEqual(day_data["day_hours"], 1.5)
