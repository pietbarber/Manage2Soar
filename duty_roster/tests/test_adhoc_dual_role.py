"""Tests for ad-hoc operations dual role prevention (Issue #589).

Ensures that:
1. A member cannot sign up as both towpilot and instructor for the same ad-hoc day
2. Members can rescind their signup to switch roles
3. Rescind functionality works for all duty roles
"""

from datetime import date, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from duty_roster.models import DutyAssignment
from logsheet.models import Airfield

User = get_user_model()


class TestAdHocDualRolePrevention(TestCase):
    """Test dual role prevention for ad-hoc operations days."""

    def setUp(self):
        self.client = Client()
        self.tomorrow = date.today() + timedelta(days=1)

        # Create a dual-qualified member (towpilot AND instructor)
        self.dual_member = User.objects.create_user(
            username="dualmember",
            email="dual@example.com",
            password="testpass123",
            first_name="Dual",
            last_name="Member",
            membership_status="Full Member",
            towpilot=True,
            instructor=True,
        )

        # Create a tow-only member
        self.tow_member = User.objects.create_user(
            username="towmember",
            email="tow@example.com",
            password="testpass123",
            first_name="Tow",
            last_name="Member",
            membership_status="Full Member",
            towpilot=True,
            instructor=False,
        )

        # Create an instructor-only member
        self.instructor_member = User.objects.create_user(
            username="instmember",
            email="inst@example.com",
            password="testpass123",
            first_name="Instructor",
            last_name="Member",
            membership_status="Full Member",
            towpilot=False,
            instructor=True,
        )

        # Create required airfield
        self.airfield = Airfield.objects.create(identifier="KFRR", name="Test Airfield")

        # Create an ad-hoc day (is_scheduled=False)
        self.adhoc_assignment = DutyAssignment.objects.create(
            date=self.tomorrow,
            is_scheduled=False,
            is_confirmed=False,
        )

    def test_dual_member_can_signup_as_towpilot(self):
        """Test that a dual-qualified member can sign up as tow pilot."""
        self.client.login(username="dualmember", password="testpass123")

        url = reverse(
            "duty_roster:calendar_tow_signup",
            args=[self.tomorrow.year, self.tomorrow.month, self.tomorrow.day],
        )
        response = self.client.post(url)

        self.assertEqual(response.status_code, 200)
        self.adhoc_assignment.refresh_from_db()
        self.assertEqual(self.adhoc_assignment.tow_pilot, self.dual_member)

    def test_dual_member_can_signup_as_instructor(self):
        """Test that a dual-qualified member can sign up as instructor."""
        self.client.login(username="dualmember", password="testpass123")

        url = reverse(
            "duty_roster:calendar_instructor_signup",
            args=[self.tomorrow.year, self.tomorrow.month, self.tomorrow.day],
        )
        response = self.client.post(url)

        self.assertEqual(response.status_code, 200)
        self.adhoc_assignment.refresh_from_db()
        self.assertEqual(self.adhoc_assignment.instructor, self.dual_member)

    def test_cannot_signup_as_instructor_when_already_towpilot(self):
        """Test that a member who signed up as tow cannot also sign up as instructor."""
        self.client.login(username="dualmember", password="testpass123")

        # First, sign up as tow pilot
        self.adhoc_assignment.tow_pilot = self.dual_member
        self.adhoc_assignment.save()

        # Try to sign up as instructor
        url = reverse(
            "duty_roster:calendar_instructor_signup",
            args=[self.tomorrow.year, self.tomorrow.month, self.tomorrow.day],
        )
        response = self.client.post(url)

        # Should return forbidden
        self.assertEqual(response.status_code, 403)
        self.assertIn("already signed up as", response.content.decode())

        # Instructor should still be None
        self.adhoc_assignment.refresh_from_db()
        self.assertIsNone(self.adhoc_assignment.instructor)

    def test_cannot_signup_as_towpilot_when_already_instructor(self):
        """Test that a member who signed up as instructor cannot also sign up as tow."""
        self.client.login(username="dualmember", password="testpass123")

        # First, sign up as instructor
        self.adhoc_assignment.instructor = self.dual_member
        self.adhoc_assignment.save()

        # Try to sign up as tow pilot
        url = reverse(
            "duty_roster:calendar_tow_signup",
            args=[self.tomorrow.year, self.tomorrow.month, self.tomorrow.day],
        )
        response = self.client.post(url)

        # Should return forbidden
        self.assertEqual(response.status_code, 403)
        self.assertIn("already signed up as", response.content.decode())

        # Tow pilot should still be None
        self.adhoc_assignment.refresh_from_db()
        self.assertIsNone(self.adhoc_assignment.tow_pilot)

    def test_dual_role_prevention_only_applies_to_adhoc_days(self):
        """Test that scheduled days don't have the dual role restriction."""
        # Create a scheduled day
        day_after = self.tomorrow + timedelta(days=1)
        scheduled_assignment = DutyAssignment.objects.create(
            date=day_after,
            is_scheduled=True,
            is_confirmed=True,
            instructor=self.dual_member,  # Already assigned as instructor
        )

        self.client.login(username="dualmember", password="testpass123")

        # Try to sign up as tow pilot on scheduled day
        url = reverse(
            "duty_roster:calendar_tow_signup",
            args=[day_after.year, day_after.month, day_after.day],
        )
        response = self.client.post(url)

        # Should succeed (no dual role prevention on scheduled days)
        self.assertEqual(response.status_code, 200)
        scheduled_assignment.refresh_from_db()
        self.assertEqual(scheduled_assignment.tow_pilot, self.dual_member)


class TestAdHocRescindFunctionality(TestCase):
    """Test rescind functionality for ad-hoc operations days."""

    def setUp(self):
        self.client = Client()
        self.tomorrow = date.today() + timedelta(days=1)

        # Create members with different roles
        self.tow_member = User.objects.create_user(
            username="towmember",
            email="tow@example.com",
            password="testpass123",
            first_name="Tow",
            last_name="Member",
            membership_status="Full Member",
            towpilot=True,
        )

        self.instructor_member = User.objects.create_user(
            username="instmember",
            email="inst@example.com",
            password="testpass123",
            first_name="Instructor",
            last_name="Member",
            membership_status="Full Member",
            instructor=True,
        )

        self.do_member = User.objects.create_user(
            username="domember",
            email="do@example.com",
            password="testpass123",
            first_name="Duty",
            last_name="Officer",
            membership_status="Full Member",
            duty_officer=True,
        )

        self.ado_member = User.objects.create_user(
            username="adomember",
            email="ado@example.com",
            password="testpass123",
            first_name="Assistant",
            last_name="DO",
            membership_status="Full Member",
            assistant_duty_officer=True,
        )

        # Create required airfield
        self.airfield = Airfield.objects.create(identifier="KFRR", name="Test Airfield")

        # Create an ad-hoc day with all roles filled
        self.adhoc_assignment = DutyAssignment.objects.create(
            date=self.tomorrow,
            is_scheduled=False,
            is_confirmed=False,
            tow_pilot=self.tow_member,
            instructor=self.instructor_member,
            duty_officer=self.do_member,
            assistant_duty_officer=self.ado_member,
        )

    def test_tow_pilot_can_rescind(self):
        """Test that a tow pilot can rescind their signup."""
        self.client.login(username="towmember", password="testpass123")

        url = reverse(
            "duty_roster:calendar_tow_rescind",
            args=[self.tomorrow.year, self.tomorrow.month, self.tomorrow.day],
        )
        response = self.client.post(url)

        self.assertEqual(response.status_code, 200)
        self.adhoc_assignment.refresh_from_db()
        self.assertIsNone(self.adhoc_assignment.tow_pilot)

    def test_instructor_can_rescind(self):
        """Test that an instructor can rescind their signup."""
        self.client.login(username="instmember", password="testpass123")

        url = reverse(
            "duty_roster:calendar_instructor_rescind",
            args=[self.tomorrow.year, self.tomorrow.month, self.tomorrow.day],
        )
        response = self.client.post(url)

        self.assertEqual(response.status_code, 200)
        self.adhoc_assignment.refresh_from_db()
        self.assertIsNone(self.adhoc_assignment.instructor)

    def test_duty_officer_can_rescind(self):
        """Test that a duty officer can rescind their signup."""
        self.client.login(username="domember", password="testpass123")

        url = reverse(
            "duty_roster:calendar_dutyofficer_rescind",
            args=[self.tomorrow.year, self.tomorrow.month, self.tomorrow.day],
        )
        response = self.client.post(url)

        self.assertEqual(response.status_code, 200)
        self.adhoc_assignment.refresh_from_db()
        self.assertIsNone(self.adhoc_assignment.duty_officer)

    def test_ado_can_rescind(self):
        """Test that an ADO can rescind their signup."""
        self.client.login(username="adomember", password="testpass123")

        url = reverse(
            "duty_roster:calendar_ado_rescind",
            args=[self.tomorrow.year, self.tomorrow.month, self.tomorrow.day],
        )
        response = self.client.post(url)

        self.assertEqual(response.status_code, 200)
        self.adhoc_assignment.refresh_from_db()
        self.assertIsNone(self.adhoc_assignment.assistant_duty_officer)

    def test_cannot_rescind_if_not_signed_up(self):
        """Test that a member cannot rescind if they're not signed up."""
        # Create another tow pilot
        other_member = User.objects.create_user(
            username="othertow",
            email="other@example.com",
            password="testpass123",
            first_name="Other",
            last_name="Pilot",
            membership_status="Full Member",
            towpilot=True,
        )

        self.client.login(username="othertow", password="testpass123")

        url = reverse(
            "duty_roster:calendar_tow_rescind",
            args=[self.tomorrow.year, self.tomorrow.month, self.tomorrow.day],
        )
        response = self.client.post(url)

        self.assertEqual(response.status_code, 403)
        self.assertIn("not the tow pilot", response.content.decode())

    def test_cannot_rescind_on_scheduled_day(self):
        """Test that rescind doesn't work on scheduled days."""
        # Create a scheduled day
        day_after = self.tomorrow + timedelta(days=1)
        scheduled_assignment = DutyAssignment.objects.create(
            date=day_after,
            is_scheduled=True,
            is_confirmed=True,
            tow_pilot=self.tow_member,
        )

        self.client.login(username="towmember", password="testpass123")

        url = reverse(
            "duty_roster:calendar_tow_rescind",
            args=[day_after.year, day_after.month, day_after.day],
        )
        response = self.client.post(url)

        self.assertEqual(response.status_code, 403)
        self.assertIn("scheduled operations", response.content.decode())

        # Should still be assigned
        scheduled_assignment.refresh_from_db()
        self.assertEqual(scheduled_assignment.tow_pilot, self.tow_member)


class TestRescindThenSwitchRoles(TestCase):
    """Test the workflow of rescinding one role to switch to another."""

    def setUp(self):
        self.client = Client()
        self.tomorrow = date.today() + timedelta(days=1)

        # Create a dual-qualified member
        self.dual_member = User.objects.create_user(
            username="dualmember",
            email="dual@example.com",
            password="testpass123",
            first_name="Dual",
            last_name="Member",
            membership_status="Full Member",
            towpilot=True,
            instructor=True,
        )

        # Create required airfield
        self.airfield = Airfield.objects.create(identifier="KFRR", name="Test Airfield")

        # Create an ad-hoc day with dual member as tow pilot
        self.adhoc_assignment = DutyAssignment.objects.create(
            date=self.tomorrow,
            is_scheduled=False,
            is_confirmed=False,
            tow_pilot=self.dual_member,
        )

    def test_can_rescind_tow_then_signup_as_instructor(self):
        """Test that a member can rescind tow signup and then sign up as instructor."""
        self.client.login(username="dualmember", password="testpass123")

        # First, rescind as tow pilot
        rescind_url = reverse(
            "duty_roster:calendar_tow_rescind",
            args=[self.tomorrow.year, self.tomorrow.month, self.tomorrow.day],
        )
        response = self.client.post(rescind_url)
        self.assertEqual(response.status_code, 200)

        self.adhoc_assignment.refresh_from_db()
        self.assertIsNone(self.adhoc_assignment.tow_pilot)

        # Now sign up as instructor
        signup_url = reverse(
            "duty_roster:calendar_instructor_signup",
            args=[self.tomorrow.year, self.tomorrow.month, self.tomorrow.day],
        )
        response = self.client.post(signup_url)
        self.assertEqual(response.status_code, 200)

        self.adhoc_assignment.refresh_from_db()
        self.assertEqual(self.adhoc_assignment.instructor, self.dual_member)

    def test_can_rescind_instructor_then_signup_as_tow(self):
        """Test that a member can rescind instructor signup and then sign up as tow."""
        # Set up with instructor instead
        self.adhoc_assignment.tow_pilot = None
        self.adhoc_assignment.instructor = self.dual_member
        self.adhoc_assignment.save()

        self.client.login(username="dualmember", password="testpass123")

        # First, rescind as instructor
        rescind_url = reverse(
            "duty_roster:calendar_instructor_rescind",
            args=[self.tomorrow.year, self.tomorrow.month, self.tomorrow.day],
        )
        response = self.client.post(rescind_url)
        self.assertEqual(response.status_code, 200)

        self.adhoc_assignment.refresh_from_db()
        self.assertIsNone(self.adhoc_assignment.instructor)

        # Now sign up as tow pilot
        signup_url = reverse(
            "duty_roster:calendar_tow_signup",
            args=[self.tomorrow.year, self.tomorrow.month, self.tomorrow.day],
        )
        response = self.client.post(signup_url)
        self.assertEqual(response.status_code, 200)

        self.adhoc_assignment.refresh_from_db()
        self.assertEqual(self.adhoc_assignment.tow_pilot, self.dual_member)


class TestRescindRequiresAuthentication(TestCase):
    """Test that rescind views require authentication."""

    def setUp(self):
        self.client = Client()
        self.tomorrow = date.today() + timedelta(days=1)

        # Create an ad-hoc day
        DutyAssignment.objects.create(
            date=self.tomorrow,
            is_scheduled=False,
            is_confirmed=False,
        )

    def test_tow_rescind_requires_auth(self):
        """Test that tow rescind requires authentication."""
        url = reverse(
            "duty_roster:calendar_tow_rescind",
            args=[self.tomorrow.year, self.tomorrow.month, self.tomorrow.day],
        )
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_instructor_rescind_requires_auth(self):
        """Test that instructor rescind requires authentication."""
        url = reverse(
            "duty_roster:calendar_instructor_rescind",
            args=[self.tomorrow.year, self.tomorrow.month, self.tomorrow.day],
        )
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)

    def test_dutyofficer_rescind_requires_auth(self):
        """Test that duty officer rescind requires authentication."""
        url = reverse(
            "duty_roster:calendar_dutyofficer_rescind",
            args=[self.tomorrow.year, self.tomorrow.month, self.tomorrow.day],
        )
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)

    def test_ado_rescind_requires_auth(self):
        """Test that ADO rescind requires authentication."""
        url = reverse(
            "duty_roster:calendar_ado_rescind",
            args=[self.tomorrow.year, self.tomorrow.month, self.tomorrow.day],
        )
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
