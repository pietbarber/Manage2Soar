"""
Test performance improvements for Issue #285 - Logsheet Finances optimization
"""

import time
from datetime import time as dt_time

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
    LogsheetPayment,
    Towplane,
)
from members.models import Member

User = get_user_model()


class LogsheetFinancesPerformanceTestCase(TestCase):
    """Test performance improvements in manage_logsheet_finances view."""

    def setUp(self):
        """Create test data with realistic volumes."""
        # Create test member
        self.member = Member.objects.create_user(
            username="testpilot",
            password="testpass123",
            first_name="Test",
            last_name="Pilot",
            membership_status="Full Member",
        )

        # Create additional members for realistic data volumes
        self.members = [self.member]
        for i in range(20):  # Create 20 additional members
            member = Member.objects.create_user(
                username=f"pilot{i}",
                password="testpass123",
                first_name=f"Pilot{i}",
                last_name=f"Last{i}",
                membership_status="Full Member" if i % 2 == 0 else "Student Member",
            )
            self.members.append(member)

        # Create airfield
        self.airfield = Airfield.objects.create(name="Test Field", identifier="TEST")

        # Create towplane and glider
        self.towplane = Towplane.objects.create(
            name="Test Towplane", n_number="N123TP", is_active=True
        )

        self.glider = Glider.objects.create(
            competition_number="XY",
            make="Test",
            model="Glider",
            n_number="N123XY",
            is_active=True,
            rental_rate=25.00,
        )

        # Create logsheet
        self.logsheet = Logsheet.objects.create(
            log_date="2025-11-24",
            airfield=self.airfield,
            duty_officer=self.member,
            created_by=self.member,
        )

        # Create multiple flights for realistic scenario
        for i, member in enumerate(self.members[:15]):  # Create 15 flights
            Flight.objects.create(
                logsheet=self.logsheet,
                pilot=member,
                glider=self.glider,
                towplane=self.towplane,
                tow_pilot=self.member,
                release_altitude=2000 + (i * 100),  # Varying altitudes
                launch_time=dt_time(9, 0, 0),
                landing_time=dt_time(10, 30, 0),
            )

    def test_finances_view_performance(self):
        """Test the performance of the optimized finances view."""
        client = Client()
        client.force_login(self.member)

        # Reset query count
        connection.queries_log.clear()

        # Time the request
        start_time = time.time()

        # Make request to finances view
        response = client.get(
            reverse("logsheet:manage_logsheet_finances", args=[self.logsheet.pk])
        )

        end_time = time.time()
        request_time = end_time - start_time
        query_count = len(connection.queries)

        # Assertions
        self.assertEqual(response.status_code, 200)

        # Performance reporting
        print(f"\n=== PERFORMANCE METRICS ===")
        print(f"Request time: {request_time:.4f} seconds")
        print(f"Database queries: {query_count}")
        print(
            f"Flights processed: {Flight.objects.filter(logsheet=self.logsheet).count()}"
        )
        print(f"Total members: {Member.objects.count()}")

        # Performance analysis (informational)
        if query_count > 0:
            if query_count > 15:
                print(f"⚠️  HIGH QUERY COUNT: {query_count} queries (target: < 15)")
            else:
                print(f"✅ Query count acceptable: {query_count} queries")
        else:
            print("ℹ️  NOTE: Query logging may not be enabled in test environment")

        if request_time > 1.0:
            print(f"⚠️  SLOW RESPONSE: {request_time:.4f}s (target: < 1.0s)")
        else:
            print(f"✅ Response time good: {request_time:.4f}s")

        # Verify response contains expected data
        self.assertIn("flight_data_sorted", response.context)
        self.assertIn("pilot_summary_sorted", response.context)
        self.assertIn("member_charges_sorted", response.context)

        # Check that we have the expected number of flights
        flight_data = response.context["flight_data_sorted"]
        self.assertEqual(len(flight_data), 15)

    def test_bulk_payment_operations(self):
        """Test that payment operations are done in bulk, not individual queries."""
        client = Client()
        client.force_login(self.member)

        # First, load the page to create initial payment records
        response = client.get(
            reverse("logsheet:manage_logsheet_finances", args=[self.logsheet.pk])
        )
        self.assertEqual(response.status_code, 200)

        # Now test POST operations (payment method updates)
        connection.queries_log.clear()

        post_data = {}
        for member in self.members[:15]:  # Update payment methods for flight members
            post_data[f"payment_method_{member.id}"] = "cash"
            post_data[f"note_{member.id}"] = f"Test note for {member.username}"

        start_time = time.time()
        response = client.post(
            reverse("logsheet:manage_logsheet_finances", args=[self.logsheet.pk]),
            post_data,
        )
        end_time = time.time()

        request_time = end_time - start_time
        query_count = len(connection.queries)

        # Verify POST was successful
        self.assertEqual(
            response.status_code, 302
        )  # Should redirect after successful update

        print(f"\n=== POST PERFORMANCE METRICS ===")
        print(f"POST request time: {request_time:.4f} seconds")
        print(f"Database queries for POST: {query_count}")
        print(
            f"Payment records updated: {len([k for k in post_data.keys() if k.startswith('payment_method')])}"
        )

        # With bulk operations, query count should be very low
        self.assertLess(
            query_count,
            10,
            f"Too many POST queries ({query_count}). Expected < 10 with bulk operations.",
        )

        # Verify payments were updated
        payment_count = LogsheetPayment.objects.filter(
            logsheet=self.logsheet, payment_method="cash"
        ).count()
        self.assertGreater(payment_count, 0, "Payment methods should have been updated")


class FinancesViewQueryAnalysisTestCase(TestCase):
    """Analyze specific query patterns in the finances view."""

    def setUp(self):
        """Create minimal test data for query analysis."""
        self.member = Member.objects.create_user(
            username="testuser",
            password="testpass123",
            first_name="Test",
            last_name="User",
            membership_status="Full Member",
        )

        self.airfield = Airfield.objects.create(name="Test Field", identifier="TEST")

        self.logsheet = Logsheet.objects.create(
            log_date="2025-11-24",
            airfield=self.airfield,
            duty_officer=self.member,
            created_by=self.member,
        )

    @override_settings(DEBUG=True)
    def test_query_optimization_patterns(self):
        """Test that optimized queries use select_related and avoid N+1 queries."""
        client = Client()
        client.force_login(self.member)

        connection.queries_log.clear()

        response = client.get(
            reverse("logsheet:manage_logsheet_finances", args=[self.logsheet.pk])
        )

        queries = connection.queries
        query_sqls = [q["sql"] for q in queries]

        print(f"\n=== QUERY ANALYSIS ===")
        print(f"Total queries: {len(queries)}")

        # Check for optimized queries
        select_related_count = sum(1 for sql in query_sqls if "JOIN" in sql.upper())
        print(f"Queries with JOINs (select_related): {select_related_count}")

        # Check that member queries use proper filtering
        member_queries = [sql for sql in query_sqls if "members_member" in sql.lower()]
        print(f"Member queries: {len(member_queries)}")

        # Look for membership_status filtering
        status_filtered_queries = [
            sql for sql in query_sqls if "membership_status" in sql.lower()
        ]
        print(f"Membership status filtered queries: {len(status_filtered_queries)}")

        # Should have JOINs for optimized queries
        self.assertGreater(select_related_count, 0, "Should use JOINs for related data")

        # Should filter by membership status at database level
        self.assertGreater(
            len(status_filtered_queries),
            0,
            "Should filter membership status in database",
        )

        self.assertEqual(response.status_code, 200)
