from datetime import date, time, timedelta

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from duty_roster.models import (
    DutyAssignment,
    DutyPreference,
    DutyRoleDefinition,
    MemberBlackout,
)
from duty_roster.views import (
    _calculate_membership_duration,
    _has_performed_duty_detailed,
    calendar_refresh_response,
)
from logsheet.models import Airfield, Flight, Glider, Logsheet
from members.models import Member
from siteconfig.models import SiteConfiguration

User = get_user_model()


class DutyDelinquentsDetailViewTests(TestCase):
    def setUp(self):
        """Set up test data"""
        self.client = Client()

        # Create test airfield
        self.airfield = Airfield.objects.create(name="Test Field", identifier="TEST")

        # Create test glider
        self.glider = Glider.objects.create(
            make="Test", model="Glider", n_number="N12345", competition_number="ABC"
        )

        # Create members with different permission levels
        self.regular_member = Member.objects.create(
            username="regular",
            email="regular@test.com",
            first_name="Regular",
            last_name="Member",
            membership_status="Full Member",
            joined_club=date.today() - timedelta(days=365),
        )

        self.rostermeister = Member.objects.create(
            username="rostermeister",
            email="roster@test.com",
            first_name="Roster",
            last_name="Meister",
            membership_status="Full Member",
            rostermeister=True,
            joined_club=date.today() - timedelta(days=365),
        )

        self.member_manager = Member.objects.create(
            username="membermanager",
            email="member@test.com",
            first_name="Member",
            last_name="Manager",
            membership_status="Full Member",
            member_manager=True,
            joined_club=date.today() - timedelta(days=365),
        )

        self.director = Member.objects.create(
            username="director",
            email="director@test.com",
            first_name="Director",
            last_name="Person",
            membership_status="Full Member",
            director=True,
            joined_club=date.today() - timedelta(days=365),
        )

        self.superuser = Member.objects.create(
            username="superuser",
            email="super@test.com",
            first_name="Super",
            last_name="User",
            membership_status="Full Member",
            is_superuser=True,
            joined_club=date.today() - timedelta(days=365),
        )

        # Create a delinquent member - one who flies but doesn't do duty
        self.delinquent_member = Member.objects.create(
            username="delinquent",
            email="delinquent@test.com",
            first_name="Delinquent",
            last_name="Flyer",
            membership_status="Full Member",
            instructor=True,
            towpilot=True,
            joined_club=date.today() - timedelta(days=365),
        )

        # Create recent flights for delinquent member
        for i in range(5):
            flight_date = date.today() - timedelta(days=30 * i)
            logsheet = Logsheet.objects.create(
                log_date=flight_date,
                airfield=self.airfield,
                created_by=self.delinquent_member,
                finalized=True,
            )
            Flight.objects.create(
                pilot=self.delinquent_member,
                glider=self.glider,
                logsheet=logsheet,
                launch_time=time(10, 0, 0),
                landing_time=time(11, 0, 0),
            )

    def test_permission_required_regular_member(self):
        """Regular members should not have access"""
        self.client.force_login(self.regular_member)
        response = self.client.get(reverse("duty_roster:duty_delinquents_detail"))
        # Should redirect to login or show permission denied
        self.assertNotEqual(response.status_code, 200)

    def test_permission_allowed_rostermeister(self):
        """Rostermeister should have access"""
        self.client.force_login(self.rostermeister)
        response = self.client.get(reverse("duty_roster:duty_delinquents_detail"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Duty Delinquents Detail Report")

    def test_permission_allowed_member_manager(self):
        """Member manager should have access"""
        self.client.force_login(self.member_manager)
        response = self.client.get(reverse("duty_roster:duty_delinquents_detail"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Duty Delinquents Detail Report")

    def test_permission_allowed_director(self):
        """Director should have access"""
        self.client.force_login(self.director)
        response = self.client.get(reverse("duty_roster:duty_delinquents_detail"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Duty Delinquents Detail Report")

    def test_permission_allowed_superuser(self):
        """Superuser should have access"""
        self.client.force_login(self.superuser)
        response = self.client.get(reverse("duty_roster:duty_delinquents_detail"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Duty Delinquents Detail Report")

    def test_delinquent_member_appears_in_report(self):
        """Delinquent member should appear in the report"""
        self.client.force_login(self.rostermeister)
        response = self.client.get(reverse("duty_roster:duty_delinquents_detail"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.delinquent_member.full_display_name)
        self.assertContains(response, self.delinquent_member.email)

        # Should show flight count
        self.assertContains(response, "5 flights")

        # Should show roles
        self.assertContains(response, "Instructor")
        self.assertContains(response, "Tow Pilot")

    def test_dynamic_enabled_uses_configured_dynamic_role_labels(self):
        SiteConfiguration.objects.create(
            club_name="Test Club",
            domain_name="test.org",
            club_abbreviation="TC",
            enable_dynamic_duty_roles=True,
            schedule_instructors=False,
            schedule_tow_pilots=False,
            schedule_duty_officers=False,
            schedule_assistant_duty_officers=False,
            schedule_commercial_pilots=False,
        )
        site_config = SiteConfiguration.objects.first()
        assert site_config is not None

        DutyRoleDefinition.objects.create(
            site_configuration=site_config,
            key="am_tow",
            display_name="AM Tow",
            legacy_role_key="towpilot",
            is_active=True,
            sort_order=10,
        )
        DutyRoleDefinition.objects.create(
            site_configuration=site_config,
            key="pm_tow",
            display_name="PM Tow",
            legacy_role_key="towpilot",
            is_active=True,
            sort_order=20,
        )

        self.client.force_login(self.rostermeister)
        response = self.client.get(reverse("duty_roster:duty_delinquents_detail"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "AM Tow")
        self.assertContains(response, "PM Tow")

    def test_dynamic_enabled_without_commercial_role_hides_commercial_label(self):
        self.delinquent_member.glider_rating = "commercial"
        self.delinquent_member.save()

        SiteConfiguration.objects.create(
            club_name="Test Club",
            domain_name="test.org",
            club_abbreviation="TC",
            enable_dynamic_duty_roles=True,
            schedule_instructors=True,
            schedule_tow_pilots=False,
            schedule_duty_officers=False,
            schedule_assistant_duty_officers=False,
            schedule_commercial_pilots=True,
        )
        site_config = SiteConfiguration.objects.first()
        assert site_config is not None

        DutyRoleDefinition.objects.create(
            site_configuration=site_config,
            key="am_instructor",
            display_name="AM Instructor",
            legacy_role_key="instructor",
            is_active=True,
            sort_order=10,
        )

        self.client.force_login(self.rostermeister)
        response = self.client.get(reverse("duty_roster:duty_delinquents_detail"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "AM Instructor")
        self.assertNotContains(response, "Commercial Pilot")

    def test_member_with_recent_duty_not_in_report(self):
        """Member who has done recent duty should not appear"""
        # Simulate the delinquent member having performed recent duty via a Logsheet entry
        # Use an existing, finalized logsheet from setUp and assign the member as duty instructor
        # so the delinquency logic treats them as having recently served duty
        recent_logsheet = Logsheet.objects.filter(
            log_date__gte=date.today() - timedelta(days=90), finalized=True
        ).first()

        # Ensure we found a logsheet (using TestCase assertion for robustness)
        self.assertIsNotNone(recent_logsheet, "No recent logsheet found in test setup")
        assert recent_logsheet is not None  # Type narrowing for Pylance

        # Update the logsheet to assign delinquent member as duty instructor
        recent_logsheet.duty_instructor = self.delinquent_member
        recent_logsheet.save()

        self.client.force_login(self.rostermeister)
        response = self.client.get(reverse("duty_roster:duty_delinquents_detail"))

        self.assertEqual(response.status_code, 200)
        # Should not contain the delinquent member anymore
        self.assertNotContains(response, self.delinquent_member.full_display_name)

    def test_inactive_member_not_in_report(self):
        """Inactive members should be excluded"""
        self.delinquent_member.membership_status = "Inactive"
        self.delinquent_member.save()

        self.client.force_login(self.rostermeister)
        response = self.client.get(reverse("duty_roster:duty_delinquents_detail"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.delinquent_member.full_display_name)

    def test_member_blackouts_display(self):
        """Member blackouts should be displayed"""
        # Add current and recent blackouts
        MemberBlackout.objects.create(
            member=self.delinquent_member,
            date=date.today() + timedelta(days=30),
            note="Vacation planned",
        )
        MemberBlackout.objects.create(
            member=self.delinquent_member,
            date=date.today() - timedelta(days=60),
            note="Was traveling",
        )

        self.client.force_login(self.rostermeister)
        response = self.client.get(reverse("duty_roster:duty_delinquents_detail"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Vacation planned")
        self.assertContains(response, "Was traveling")

    def test_suspended_member_indication(self):
        """Suspended members should show suspension status"""
        DutyPreference.objects.create(
            member=self.delinquent_member,
            scheduling_suspended=True,
            suspended_reason="Medical issue",
        )

        self.client.force_login(self.rostermeister)
        response = self.client.get(reverse("duty_roster:duty_delinquents_detail"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Scheduling Suspended")
        self.assertContains(response, "Medical issue")

    def test_no_delinquents_message(self):
        """Should show success message when no delinquents found"""
        # Remove flights from delinquent member
        Flight.objects.filter(pilot=self.delinquent_member).delete()

        self.client.force_login(self.rostermeister)
        response = self.client.get(reverse("duty_roster:duty_delinquents_detail"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Great news!")
        self.assertContains(response, "No duty delinquents found")

    def test_treasurer_exempt_from_delinquency(self):
        """Treasurer should be exempt from duty delinquency report"""
        # Create a treasurer who flies but doesn't do duty
        treasurer = Member.objects.create(
            username="treasurer",
            email="treasurer@test.com",
            first_name="Club",
            last_name="Treasurer",
            membership_status="Full Member",
            treasurer=True,
            joined_club=date.today() - timedelta(days=365),
        )

        # Create recent flights for treasurer (use different airfield to avoid conflicts)
        treasurer_airfield = Airfield.objects.create(
            name="Treasurer Field", identifier="TREA"
        )
        for i in range(5):
            flight_date = date.today() - timedelta(days=30 * i)
            logsheet = Logsheet.objects.create(
                log_date=flight_date,
                airfield=treasurer_airfield,
                created_by=treasurer,
                finalized=True,
            )
            Flight.objects.create(
                pilot=treasurer,
                glider=self.glider,
                logsheet=logsheet,
                launch_time=time(10, 0, 0),
                landing_time=time(11, 0, 0),
            )

        self.client.force_login(self.rostermeister)
        response = self.client.get(reverse("duty_roster:duty_delinquents_detail"))

        self.assertEqual(response.status_code, 200)
        # Treasurer should NOT appear in the delinquents report
        self.assertNotContains(response, treasurer.full_display_name)
        # But the regular delinquent member should still appear
        self.assertContains(response, self.delinquent_member.full_display_name)

    def test_emeritus_exempt_from_delinquency(self):
        """Emeritus members should be exempt from duty delinquency report"""
        # Create an emeritus member who flies but doesn't do duty
        emeritus = Member.objects.create(
            username="emeritus",
            email="emeritus@test.com",
            first_name="Emeritus",
            last_name="Member",
            membership_status="Emeritus Member",
            joined_club=date.today() - timedelta(days=3650),  # Long-time member
        )

        # Create recent flights for emeritus member (use different airfield to avoid conflicts)
        emeritus_airfield = Airfield.objects.create(
            name="Emeritus Field", identifier="EMER"
        )
        for i in range(5):
            flight_date = date.today() - timedelta(days=30 * i)
            logsheet = Logsheet.objects.create(
                log_date=flight_date,
                airfield=emeritus_airfield,
                created_by=emeritus,
                finalized=True,
            )
            Flight.objects.create(
                pilot=emeritus,
                glider=self.glider,
                logsheet=logsheet,
                launch_time=time(10, 0, 0),
                landing_time=time(11, 0, 0),
            )

        self.client.force_login(self.rostermeister)
        response = self.client.get(reverse("duty_roster:duty_delinquents_detail"))

        self.assertEqual(response.status_code, 200)
        # Emeritus member should NOT appear in the delinquents report
        self.assertNotContains(response, emeritus.full_display_name)
        # But the regular delinquent member should still appear
        self.assertContains(response, self.delinquent_member.full_display_name)


class HelperFunctionTests(TestCase):
    def setUp(self):
        self.member = Member.objects.create(
            username="testmember",
            email="test@test.com",
            first_name="Test",
            last_name="Member",
            membership_status="Full Member",
            joined_club=date.today() - timedelta(days=365),
        )

    def test_has_performed_duty_detailed_no_duty(self):
        """Test helper function when member has no duty"""
        cutoff_date = date.today() - timedelta(days=365)
        result = _has_performed_duty_detailed(self.member, cutoff_date)

        self.assertFalse(result["has_duty"])
        self.assertIsNone(result["last_duty_date"])
        self.assertIsNone(result["last_duty_role"])

    def test_has_performed_duty_detailed_with_logsheet_duty(self):
        """Test helper function when member has recent logsheet duty assignment"""
        from logsheet.models import Airfield, Logsheet

        airfield = Airfield.objects.create(name="Test Field", identifier="TEST")
        duty_date = date.today() - timedelta(days=30)
        # Create actual logsheet duty (not just scheduled DutyAssignment)
        Logsheet.objects.create(
            log_date=duty_date,
            airfield=airfield,
            created_by=self.member,
            finalized=True,
            duty_officer=self.member,  # Member actually served as duty officer
        )

        cutoff_date = date.today() - timedelta(days=365)
        result = _has_performed_duty_detailed(self.member, cutoff_date)

        self.assertTrue(result["has_duty"])
        self.assertEqual(result["last_duty_date"], duty_date)
        self.assertEqual(result["last_duty_role"], "Duty Officer")
        self.assertEqual(result["last_duty_type"], "Logsheet Duty")

    def test_has_performed_duty_detailed_with_instruction_flight(self):
        """Test helper function when member has performed actual instruction"""
        from logsheet.models import Airfield, Flight, Glider, Logsheet

        # Create test data
        airfield = Airfield.objects.create(name="Test Field", identifier="TEST")
        glider = Glider.objects.create(make="Test", model="Glider", n_number="N12345")

        flight_date = date.today() - timedelta(days=30)
        logsheet = Logsheet.objects.create(
            log_date=flight_date,
            airfield=airfield,
            created_by=self.member,
            finalized=True,
        )

        # Create flight where member was instructor
        Flight.objects.create(
            pilot=self.member,  # Different member as pilot
            instructor=self.member,  # Our test member as instructor
            glider=glider,
            logsheet=logsheet,
            launch_time=time(10, 0, 0),
            landing_time=time(11, 0, 0),
        )

        cutoff_date = date.today() - timedelta(days=365)
        result = _has_performed_duty_detailed(self.member, cutoff_date)

        self.assertTrue(result["has_duty"])
        self.assertEqual(result["last_duty_date"], flight_date)
        self.assertEqual(result["last_duty_role"], "Instructor (Flight)")
        self.assertEqual(result["last_duty_type"], "Flight Activity")
        self.assertEqual(result["flight_count"], 1)

    def test_calculate_membership_duration_with_join_date(self):
        """Test membership duration calculation with join date"""
        join_date = date.today() - timedelta(days=400)  # About 13 months
        self.member.joined_club = join_date
        self.member.save()

        duration = _calculate_membership_duration(self.member, date.today())
        self.assertIn("1 year", duration)
        self.assertIn("month", duration)

    def test_calculate_membership_duration_no_join_date(self):
        """Test membership duration calculation without join date"""
        self.member.joined_club = None
        self.member.save()

        duration = _calculate_membership_duration(self.member, date.today())
        self.assertEqual(duration, "Unknown (no join date)")


class CalendarRefreshResponseTests(TestCase):
    """Test the calendar_refresh_response helper function"""

    def test_calendar_refresh_response_headers(self):
        """Test that calendar_refresh_response sets correct HX-Trigger header"""
        year, month = 2024, 12
        response = calendar_refresh_response(year, month)

        # Check response status and headers
        self.assertEqual(response.status_code, 200)
        self.assertIn("HX-Trigger", response.headers)

        # Parse the HX-Trigger JSON
        import json

        trigger_data = json.loads(response.headers["HX-Trigger"])

        # Verify structure and values
        self.assertIn("refreshCalendar", trigger_data)
        self.assertEqual(trigger_data["refreshCalendar"]["year"], 2024)
        self.assertEqual(trigger_data["refreshCalendar"]["month"], 12)

    def test_calendar_refresh_response_json_format(self):
        """Test that the JSON structure is correct"""
        year, month = 2025, 1
        response = calendar_refresh_response(year, month)

        import json

        trigger_data = json.loads(response.headers["HX-Trigger"])

        # Verify the exact expected structure
        expected_structure = {"refreshCalendar": {"year": 2025, "month": 1}}
        self.assertEqual(trigger_data, expected_structure)

    def test_calendar_refresh_response_type_conversion(self):
        """Test that string year/month are converted to integers"""
        year, month = "2023", "11"  # Pass as strings
        response = calendar_refresh_response(year, month)

        import json

        trigger_data = json.loads(response.headers["HX-Trigger"])

        # Should be converted to integers
        self.assertEqual(trigger_data["refreshCalendar"]["year"], 2023)
        self.assertEqual(trigger_data["refreshCalendar"]["month"], 11)
        self.assertIsInstance(trigger_data["refreshCalendar"]["year"], int)
        self.assertIsInstance(trigger_data["refreshCalendar"]["month"], int)


class InstructionSlotModelTests(TestCase):
    """Tests for the InstructionSlot model."""

    def setUp(self):
        """Set up test data"""
        self.airfield = Airfield.objects.create(name="Test Field", identifier="TEST")

        # Create instructor
        self.instructor = Member.objects.create(
            username="instructor",
            email="instructor@test.com",
            first_name="Test",
            last_name="Instructor",
            membership_status="Full Member",
            instructor=True,
        )

        # Create student
        self.student = Member.objects.create(
            username="student",
            email="student@test.com",
            first_name="Test",
            last_name="Student",
            membership_status="Student Member",
        )

        # Create future duty assignment
        from duty_roster.models import DutyAssignment

        self.future_date = date.today() + timedelta(days=7)
        self.assignment = DutyAssignment.objects.create(
            date=self.future_date,
            instructor=self.instructor,
            location=self.airfield,
        )

    def test_instruction_slot_creation(self):
        """Test creating an instruction slot."""
        from duty_roster.models import InstructionSlot

        slot = InstructionSlot.objects.create(
            assignment=self.assignment,
            student=self.student,
            instructor=self.instructor,
        )

        self.assertEqual(slot.status, "pending")
        self.assertEqual(slot.instructor_response, "pending")
        self.assertEqual(slot.student, self.student)
        self.assertEqual(slot.instructor, self.instructor)

    def test_accept_method(self):
        """Test instructor accepting a student."""
        from duty_roster.models import InstructionSlot

        slot = InstructionSlot.objects.create(
            assignment=self.assignment,
            student=self.student,
        )

        slot.accept(instructor=self.instructor, note="See you Saturday!")

        self.assertEqual(slot.status, "confirmed")
        self.assertEqual(slot.instructor_response, "accepted")
        self.assertEqual(slot.instructor, self.instructor)
        self.assertEqual(slot.instructor_note, "See you Saturday!")
        self.assertIsNotNone(slot.instructor_response_at)

    def test_reject_method(self):
        """Test instructor rejecting a student."""
        from duty_roster.models import InstructionSlot

        slot = InstructionSlot.objects.create(
            assignment=self.assignment,
            student=self.student,
            instructor=self.instructor,
        )

        slot.reject(note="Please try next week")

        self.assertEqual(slot.status, "cancelled")
        self.assertEqual(slot.instructor_response, "rejected")
        self.assertEqual(slot.instructor_note, "Please try next week")
        self.assertIsNotNone(slot.instructor_response_at)

    def test_unique_together_constraint(self):
        """Test that a student can only have one request per assignment."""
        from django.db import IntegrityError

        from duty_roster.models import InstructionSlot

        InstructionSlot.objects.create(
            assignment=self.assignment,
            student=self.student,
        )

        with self.assertRaises(IntegrityError):
            InstructionSlot.objects.create(
                assignment=self.assignment,
                student=self.student,
            )


class InstructionRequestViewTests(TestCase):
    """Tests for instruction request views."""

    def setUp(self):
        """Set up test data"""
        self.client = Client()
        self.airfield = Airfield.objects.create(name="Test Field", identifier="TEST")

        # Create instructor
        self.instructor = Member.objects.create(
            username="instructor",
            email="instructor@test.com",
            first_name="Test",
            last_name="Instructor",
            membership_status="Full Member",
            instructor=True,
        )
        self.instructor.set_password("testpass123")
        self.instructor.save()

        # Create student
        self.student = Member.objects.create(
            username="student",
            email="student@test.com",
            first_name="Test",
            last_name="Student",
            membership_status="Student Member",
        )
        self.student.set_password("testpass123")
        self.student.save()

        # Create future duty assignment
        from duty_roster.models import DutyAssignment

        self.future_date = date.today() + timedelta(days=7)
        self.assignment = DutyAssignment.objects.create(
            date=self.future_date,
            instructor=self.instructor,
            location=self.airfield,
        )

    def test_student_can_request_instruction(self):
        """Test that a student can request instruction."""
        self.client.login(username="student", password="testpass123")

        url = reverse(
            "duty_roster:request_instruction",
            kwargs={
                "year": self.future_date.year,
                "month": self.future_date.month,
                "day": self.future_date.day,
            },
        )

        response = self.client.post(url)

        # Should redirect after successful request
        self.assertEqual(response.status_code, 302)

        # Verify slot was created
        from duty_roster.models import InstructionSlot

        slot = InstructionSlot.objects.filter(
            assignment=self.assignment,
            student=self.student,
        ).first()

        self.assertIsNotNone(slot)
        assert slot is not None  # Type narrowing for Pylance
        self.assertEqual(slot.status, "pending")
        self.assertEqual(slot.instructor_response, "pending")

    def test_duplicate_request_prevented(self):
        """Test that duplicate requests are prevented."""
        from duty_roster.models import InstructionSlot

        # Create initial request
        InstructionSlot.objects.create(
            assignment=self.assignment,
            student=self.student,
            status="pending",
        )

        self.client.login(username="student", password="testpass123")

        url = reverse(
            "duty_roster:request_instruction",
            kwargs={
                "year": self.future_date.year,
                "month": self.future_date.month,
                "day": self.future_date.day,
            },
        )

        response = self.client.post(url, follow=True)

        # Should still redirect but with error message
        self.assertEqual(response.status_code, 200)

        # Should still only be one request
        count = InstructionSlot.objects.filter(
            assignment=self.assignment,
            student=self.student,
        ).count()
        self.assertEqual(count, 1)

    def test_cancelled_request_can_be_re_requested_without_duplicate_row(self):
        """Re-request should reuse cancelled slot and avoid unique-constraint errors."""
        from django.core import mail

        from duty_roster.models import InstructionSlot

        slot = InstructionSlot.objects.create(
            assignment=self.assignment,
            student=self.student,
            status="cancelled",
            instructor_response="rejected",
            instructor_note="Try next week",
            instructor_response_at=timezone.now(),
        )
        original_created_at = slot.created_at

        self.client.login(username="student", password="testpass123")

        url = reverse(
            "duty_roster:request_instruction",
            kwargs={
                "year": self.future_date.year,
                "month": self.future_date.month,
                "day": self.future_date.day,
            },
        )

        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)

        # Still one row; existing slot was reactivated to pending.
        self.assertEqual(
            InstructionSlot.objects.filter(
                assignment=self.assignment,
                student=self.student,
            ).count(),
            1,
        )

        slot.refresh_from_db()
        self.assertEqual(slot.status, "pending")
        self.assertEqual(slot.instructor_response, "pending")
        self.assertEqual(slot.instructor_note, "")
        self.assertIsNone(slot.instructor_response_at)
        self.assertGreater(slot.created_at, original_created_at)
        # Re-request should notify instructor(s), matching a fresh signup.
        self.assertEqual(len(mail.outbox), 1)

    def test_my_instruction_requests_view(self):
        """Test the my instruction requests view."""
        from duty_roster.models import InstructionSlot

        # Create a request
        InstructionSlot.objects.create(
            assignment=self.assignment,
            student=self.student,
            status="pending",
        )

        self.client.login(username="student", password="testpass123")

        url = reverse("duty_roster:my_instruction_requests")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "My Instruction Requests")
        self.assertContains(response, self.future_date.strftime("%B"))


# InstructionRequestWindowTests has been moved to
# duty_roster/tests/test_instruction_request_window.py (pytest-style).


class InstructorManagementViewTests(TestCase):
    """Tests for instructor management views."""

    def setUp(self):
        """Set up test data"""
        self.client = Client()
        self.airfield = Airfield.objects.create(name="Test Field", identifier="TEST")

        # Create instructor
        self.instructor = Member.objects.create(
            username="instructor",
            email="instructor@test.com",
            first_name="Test",
            last_name="Instructor",
            membership_status="Full Member",
            instructor=True,
        )
        self.instructor.set_password("testpass123")
        self.instructor.save()

        # Create students
        self.student1 = Member.objects.create(
            username="student1",
            email="student1@test.com",
            first_name="Alice",
            last_name="Student",
            membership_status="Student Member",
        )

        self.student2 = Member.objects.create(
            username="student2",
            email="student2@test.com",
            first_name="Bob",
            last_name="Student",
            membership_status="Student Member",
        )

        # Create future duty assignment
        from duty_roster.models import DutyAssignment

        self.future_date = date.today() + timedelta(days=7)
        self.assignment = DutyAssignment.objects.create(
            date=self.future_date,
            instructor=self.instructor,
            location=self.airfield,
        )

    def test_instructor_can_see_requests(self):
        """Test that instructor can see pending requests."""
        from duty_roster.models import InstructionSlot

        # Create pending requests
        InstructionSlot.objects.create(
            assignment=self.assignment,
            student=self.student1,
            status="pending",
        )
        InstructionSlot.objects.create(
            assignment=self.assignment,
            student=self.student2,
            status="pending",
        )

        self.client.login(username="instructor", password="testpass123")

        url = reverse("duty_roster:instructor_requests")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Alice")
        self.assertContains(response, "Bob")

    def test_instructor_can_accept_student(self):
        """Test that instructor can accept a student."""
        from duty_roster.models import InstructionSlot

        slot = InstructionSlot.objects.create(
            assignment=self.assignment,
            student=self.student1,
            status="pending",
        )

        self.client.login(username="instructor", password="testpass123")

        url = reverse("duty_roster:instructor_respond", kwargs={"slot_id": slot.id})
        response = self.client.post(url, {"action": "accept", "instructor_note": ""})

        # Should redirect
        self.assertEqual(response.status_code, 302)

        # Verify slot was updated
        slot.refresh_from_db()
        self.assertEqual(slot.status, "confirmed")
        self.assertEqual(slot.instructor_response, "accepted")
        self.assertEqual(slot.instructor, self.instructor)

    def test_instructor_can_reject_student(self):
        """Test that instructor can reject a student."""
        from duty_roster.models import InstructionSlot

        slot = InstructionSlot.objects.create(
            assignment=self.assignment,
            student=self.student1,
            status="pending",
            instructor=self.instructor,
        )

        self.client.login(username="instructor", password="testpass123")

        url = reverse("duty_roster:instructor_respond", kwargs={"slot_id": slot.id})
        response = self.client.post(
            url, {"action": "reject", "instructor_note": "Please try next week"}
        )

        # Should redirect
        self.assertEqual(response.status_code, 302)

        # Verify slot was updated
        slot.refresh_from_db()
        self.assertEqual(slot.status, "cancelled")
        self.assertEqual(slot.instructor_response, "rejected")
        self.assertEqual(slot.instructor_note, "Please try next week")

    def test_non_instructor_cannot_access(self):
        """Test that non-instructors cannot access instructor views."""
        # Create non-instructor member
        regular = Member.objects.create(
            username="regular",
            email="regular@test.com",
            first_name="Regular",
            last_name="Member",
            membership_status="Full Member",
            instructor=False,
        )
        regular.set_password("testpass123")
        regular.save()

        self.client.login(username="regular", password="testpass123")

        url = reverse("duty_roster:instructor_requests")
        response = self.client.get(url, follow=True)

        # Should redirect with error
        self.assertEqual(response.status_code, 200)

    def test_instructor_cannot_respond_to_other_days_slot(self):
        """Test that instructor can only respond to slots for their assigned days."""
        from duty_roster.models import InstructionSlot

        # Create another instructor and assignment
        other_instructor = Member.objects.create(
            username="other_instructor",
            email="other@test.com",
            first_name="Other",
            last_name="Instructor",
            membership_status="Full Member",
            instructor=True,
        )
        other_instructor.set_password("testpass123")
        other_instructor.save()

        # Create slot for self.instructor's day
        slot = InstructionSlot.objects.create(
            assignment=self.assignment,
            student=self.student1,
            status="pending",
        )

        # Log in as other_instructor who is NOT assigned to this day
        self.client.login(username="other_instructor", password="testpass123")

        url = reverse("duty_roster:instructor_respond", kwargs={"slot_id": slot.id})
        response = self.client.post(url, {"action": "accept", "instructor_note": ""})

        # Should get 403 Forbidden
        self.assertEqual(response.status_code, 403)

    def test_double_response_prevented(self):
        """Test that instructor cannot respond twice to the same request."""
        from duty_roster.models import InstructionSlot

        slot = InstructionSlot.objects.create(
            assignment=self.assignment,
            student=self.student1,
            status="pending",
            instructor_response="pending",
        )

        self.client.login(username="instructor", password="testpass123")

        # First response - should succeed
        url = reverse("duty_roster:instructor_respond", kwargs={"slot_id": slot.id})
        self.client.post(url, {"action": "accept", "instructor_note": ""})

        slot.refresh_from_db()
        self.assertEqual(slot.instructor_response, "accepted")

        # Second response - should be ignored with warning
        self.client.post(
            url, {"action": "reject", "instructor_note": "changed mind"}, follow=True
        )

        # Should still be accepted (not changed to rejected)
        slot.refresh_from_db()
        self.assertEqual(slot.instructor_response, "accepted")

    def test_invalid_action_rejected(self):
        """Test that invalid action values are rejected."""
        from duty_roster.models import InstructionSlot

        slot = InstructionSlot.objects.create(
            assignment=self.assignment,
            student=self.student1,
            status="pending",
        )

        self.client.login(username="instructor", password="testpass123")

        url = reverse("duty_roster:instructor_respond", kwargs={"slot_id": slot.id})
        response = self.client.post(
            url, {"action": "invalid_action", "instructor_note": ""}
        )

        # Should redirect (302) with error message
        self.assertEqual(response.status_code, 302)

        # Slot should remain pending
        slot.refresh_from_db()
        self.assertEqual(slot.instructor_response, "pending")


class InstructionRequestEdgeCaseTests(TestCase):
    """Additional edge case tests for instruction requests."""

    def setUp(self):
        """Set up test data"""
        self.client = Client()
        self.airfield = Airfield.objects.create(name="Test Field", identifier="TEST")

        # Create instructor
        self.instructor = Member.objects.create(
            username="instructor",
            email="instructor@test.com",
            first_name="Test",
            last_name="Instructor",
            membership_status="Full Member",
            instructor=True,
        )
        self.instructor.set_password("testpass123")
        self.instructor.save()

        # Create student
        self.student = Member.objects.create(
            username="student",
            email="student@test.com",
            first_name="Test",
            last_name="Student",
            membership_status="Student Member",
        )
        self.student.set_password("testpass123")
        self.student.save()

    def test_cannot_request_instruction_for_past_date(self):
        """Test that students cannot request instruction for past dates."""
        from duty_roster.models import DutyAssignment

        past_date = date.today() - timedelta(days=7)
        assignment = DutyAssignment.objects.create(
            date=past_date,
            instructor=self.instructor,
            location=self.airfield,
        )

        self.client.login(username="student", password="testpass123")

        url = reverse(
            "duty_roster:request_instruction",
            kwargs={
                "year": past_date.year,
                "month": past_date.month,
                "day": past_date.day,
            },
        )

        response = self.client.post(url, follow=True)

        # Should redirect with error message
        self.assertEqual(response.status_code, 200)

        # No slot should be created
        from duty_roster.models import InstructionSlot

        self.assertFalse(
            InstructionSlot.objects.filter(
                assignment=assignment, student=self.student
            ).exists()
        )

    def test_cannot_cancel_past_date_request(self):
        """Test that students cannot cancel requests for past dates."""
        from duty_roster.models import DutyAssignment, InstructionSlot

        past_date = date.today() - timedelta(days=7)
        assignment = DutyAssignment.objects.create(
            date=past_date,
            instructor=self.instructor,
            location=self.airfield,
        )

        slot = InstructionSlot.objects.create(
            assignment=assignment,
            student=self.student,
            status="pending",
        )

        self.client.login(username="student", password="testpass123")

        url = reverse(
            "duty_roster:cancel_instruction_request", kwargs={"slot_id": slot.id}
        )
        response = self.client.post(url, follow=True)

        # Should redirect with error
        self.assertEqual(response.status_code, 200)

        # Slot should still be pending (not cancelled)
        slot.refresh_from_db()
        self.assertEqual(slot.status, "pending")

    def test_cannot_cancel_already_cancelled_request(self):
        """Test that already cancelled requests show appropriate warning."""
        from duty_roster.models import DutyAssignment, InstructionSlot

        future_date = date.today() + timedelta(days=7)
        assignment = DutyAssignment.objects.create(
            date=future_date,
            instructor=self.instructor,
            location=self.airfield,
        )

        slot = InstructionSlot.objects.create(
            assignment=assignment,
            student=self.student,
            status="cancelled",
        )

        self.client.login(username="student", password="testpass123")

        url = reverse(
            "duty_roster:cancel_instruction_request", kwargs={"slot_id": slot.id}
        )
        self.client.post(url, follow=True)

        # Should still be cancelled
        slot.refresh_from_db()
        self.assertEqual(slot.status, "cancelled")

    def test_cannot_request_when_no_instructor_assigned(self):
        """Test that students cannot request when no instructor is assigned."""
        from duty_roster.models import DutyAssignment

        future_date = date.today() + timedelta(days=7)
        assignment = DutyAssignment.objects.create(
            date=future_date,
            instructor=None,
            surge_instructor=None,
            location=self.airfield,
        )

        self.client.login(username="student", password="testpass123")

        url = reverse(
            "duty_roster:request_instruction",
            kwargs={
                "year": future_date.year,
                "month": future_date.month,
                "day": future_date.day,
            },
        )

        response = self.client.post(url, follow=True)

        # Should redirect with error message
        self.assertEqual(response.status_code, 200)

        # No slot should be created
        from duty_roster.models import InstructionSlot

        self.assertFalse(
            InstructionSlot.objects.filter(
                assignment=assignment, student=self.student
            ).exists()
        )

    def test_surge_instructor_fallback(self):
        """Test that surge instructor is used when no primary instructor."""
        from duty_roster.models import DutyAssignment, InstructionSlot

        surge_instructor = Member.objects.create(
            username="surge",
            email="surge@test.com",
            first_name="Surge",
            last_name="Instructor",
            membership_status="Full Member",
            instructor=True,
        )

        future_date = date.today() + timedelta(days=7)
        assignment = DutyAssignment.objects.create(
            date=future_date,
            instructor=None,
            surge_instructor=surge_instructor,
            location=self.airfield,
        )

        self.client.login(username="student", password="testpass123")

        url = reverse(
            "duty_roster:request_instruction",
            kwargs={
                "year": future_date.year,
                "month": future_date.month,
                "day": future_date.day,
            },
        )

        self.client.post(url)

        # Should succeed and use surge instructor
        slot = InstructionSlot.objects.get(assignment=assignment, student=self.student)
        self.assertEqual(slot.instructor, surge_instructor)


class DutyPreferenceFormTests(TestCase):
    """Tests for DutyPreferenceForm validation (Issue #424)."""

    def setUp(self):
        """Set up test data."""
        # Create a member with only some duty roles (not all)
        self.partial_role_member = Member.objects.create(
            username="towpilot",
            email="towpilot@test.com",
            first_name="Tow",
            last_name="Pilot",
            membership_status="Full Member",
            towpilot=True,
            instructor=False,
            duty_officer=False,
        )
        self.partial_role_member.set_password("testpass123")
        self.partial_role_member.save()

        # Create a member with all duty roles
        self.full_role_member = Member.objects.create(
            username="fullrole",
            email="fullrole@test.com",
            first_name="Full",
            last_name="Role",
            membership_status="Full Member",
            towpilot=True,
            instructor=True,
            duty_officer=True,
        )
        self.full_role_member.set_password("testpass123")
        self.full_role_member.save()

    def test_form_handles_none_percent_values(self):
        """
        Test that form validation handles None values in percentage fields.

        Issue #424: When a member doesn't have all duty roles, the percentage
        fields for roles they don't have may be submitted as None. The form's
        clean() method should handle this gracefully without TypeError.
        """
        from duty_roster.forms import DutyPreferenceForm

        # Simulate form data where non-applicable role percentages are empty/None
        form_data = {
            "dont_schedule": False,
            "scheduling_suspended": False,
            "suspended_reason": "",
            "preferred_day": "",
            "comment": "",
            "instructor_percent": "",  # Empty - will be None
            "duty_officer_percent": "",  # Empty - will be None
            "ado_percent": "",  # Empty - will be None
            "towpilot_percent": "100",  # Member is a tow pilot
            "max_assignments_per_month": "4",
            "allow_weekend_double": False,
        }

        form = DutyPreferenceForm(data=form_data, member=self.partial_role_member)
        # This should not raise TypeError: unsupported operand type(s) for +: 'int' and 'NoneType'
        is_valid = form.is_valid()
        # Form should be valid since tow pilot is at 100%
        self.assertTrue(is_valid, f"Form errors: {form.errors}")

    def test_form_validates_total_percent_equals_100(self):
        """Test that form requires percentages to total 100% (or all 0)."""
        from duty_roster.forms import DutyPreferenceForm

        form_data = {
            "dont_schedule": False,
            "scheduling_suspended": False,
            "suspended_reason": "",
            "preferred_day": "",
            "comment": "",
            "instructor_percent": "30",
            "duty_officer_percent": "30",
            "ado_percent": "20",
            "towpilot_percent": "30",  # Total = 110%, invalid
            "max_assignments_per_month": "4",
            "allow_weekend_double": False,
        }

        form = DutyPreferenceForm(data=form_data, member=self.full_role_member)
        self.assertFalse(form.is_valid())
        self.assertIn("total duty percentages must add up to 99-100%", str(form.errors))

    def test_form_allows_all_zeros(self):
        """Test that form accepts all zeros (0% = not scheduled for duty)."""
        from duty_roster.forms import DutyPreferenceForm

        form_data = {
            "dont_schedule": False,
            "scheduling_suspended": False,
            "suspended_reason": "",
            "preferred_day": "",
            "comment": "",
            "instructor_percent": "",
            "duty_officer_percent": "",
            "ado_percent": "",
            "towpilot_percent": "",
            "max_assignments_per_month": "4",
            "allow_weekend_double": False,
        }

        form = DutyPreferenceForm(data=form_data, member=self.partial_role_member)
        # All zeros (or empty) should be valid
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")

    def test_form_allows_99_percent_rounding(self):
        """Test that form accepts 99% total (handles 33% + 66% rounding)."""
        from duty_roster.forms import DutyPreferenceForm

        form_data = {
            "dont_schedule": False,
            "scheduling_suspended": False,
            "suspended_reason": "",
            "preferred_day": "",
            "comment": "",
            "instructor_percent": "33",  # 33% + 66% = 99% (rounding issue)
            "duty_officer_percent": "0",
            "ado_percent": "0",
            "towpilot_percent": "66",
            "max_assignments_per_month": "4",
            "allow_weekend_double": False,
        }

        form = DutyPreferenceForm(data=form_data, member=self.full_role_member)
        # 99% should be valid (99-100% accepted for rounding)
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")

    def test_form_rejects_98_percent(self):
        """Test that form rejects 98% (below valid range)."""
        from duty_roster.forms import DutyPreferenceForm

        form_data = {
            "dont_schedule": False,
            "scheduling_suspended": False,
            "suspended_reason": "",
            "preferred_day": "",
            "comment": "",
            "instructor_percent": "32",  # 32% + 66% = 98% (invalid)
            "duty_officer_percent": "0",
            "ado_percent": "0",
            "towpilot_percent": "66",
            "max_assignments_per_month": "4",
            "allow_weekend_double": False,
        }

        form = DutyPreferenceForm(data=form_data, member=self.full_role_member)
        # 98% should be invalid (only 99-100% accepted)
        self.assertFalse(form.is_valid())
        self.assertIn("total duty percentages", str(form.errors).lower())

    def test_form_rejects_101_percent(self):
        """Test that form rejects 101% (above valid range)."""
        from duty_roster.forms import DutyPreferenceForm

        form_data = {
            "dont_schedule": False,
            "scheduling_suspended": False,
            "suspended_reason": "",
            "preferred_day": "",
            "comment": "",
            "instructor_percent": "34",  # 34% + 67% = 101% (invalid)
            "duty_officer_percent": "0",
            "ado_percent": "0",
            "towpilot_percent": "67",
            "max_assignments_per_month": "4",
            "allow_weekend_double": False,
        }

        form = DutyPreferenceForm(data=form_data, member=self.full_role_member)
        # 101% should be invalid (only 99-100% accepted)
        self.assertFalse(form.is_valid())
        self.assertIn("total duty percentages", str(form.errors).lower())

    def test_form_accepts_100_percent(self):
        """Test that form still accepts exactly 100%."""
        from duty_roster.forms import DutyPreferenceForm

        form_data = {
            "dont_schedule": False,
            "scheduling_suspended": False,
            "suspended_reason": "",
            "preferred_day": "",
            "comment": "",
            "instructor_percent": "25",  # 25% + 75% = 100% (valid)
            "duty_officer_percent": "0",
            "ado_percent": "0",
            "towpilot_percent": "75",
            "max_assignments_per_month": "4",
            "allow_weekend_double": False,
        }

        form = DutyPreferenceForm(data=form_data, member=self.full_role_member)
        # 100% should always be valid
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")

    def test_view_saves_none_values_as_zero(self):
        """
        Integration test: Verify blackout_manage view handles None percentage values.

        Issue #424 redux: Even after form validation passes, the view must
        ensure None values are converted to 0 before saving to the database,
        as the DutyPreference model fields don't allow NULL values.
        """
        from duty_roster.models import DutyPreference

        # Log in as the member
        self.client.login(username="towpilot", password="testpass123")

        # Create valid form data with 100% tow pilot (the only role this member has)
        # Other percentages are empty (None), which should be converted to 0
        form_data = {
            "dont_schedule": False,
            "scheduling_suspended": False,
            "suspended_reason": "",
            "preferred_day": "",
            "comment": "",
            "instructor_percent": "",  # Empty - will be None, should become 0
            "duty_officer_percent": "",  # Empty - will be None, should become 0
            "ado_percent": "",  # Empty - will be None, should become 0
            "towpilot_percent": "100",  # Member is a tow pilot at 100%
            "max_assignments_per_month": "4",
            "allow_weekend_double": False,
        }

        # POST to the blackout_manage view
        url = reverse("duty_roster:blackout_manage")
        response = self.client.post(url, data=form_data, follow=True)

        # Should succeed without IntegrityError (200 or 302 redirect)
        self.assertIn(response.status_code, [200, 302])

        # Verify the saved values: None values should be 0, tow pilot should be 100
        pref = DutyPreference.objects.get(member=self.partial_role_member)
        self.assertEqual(pref.instructor_percent, 0)
        self.assertEqual(pref.duty_officer_percent, 0)
        self.assertEqual(pref.ado_percent, 0)
        self.assertEqual(pref.towpilot_percent, 100)


class PairingPreferencesDisplayTests(TestCase):
    """Tests for pairing preferences display on blackout page (Issue #561)."""

    def setUp(self):
        """Set up test data."""
        # Create main member
        self.member = Member.objects.create(
            username="testmember",
            email="testmember@test.com",
            first_name="Test",
            last_name="Member",
            membership_status="Full Member",
        )
        self.member.set_password("testpass123")
        self.member.save()

        # Create other members for pairing
        self.pair_member1 = Member.objects.create(
            username="pair1",
            email="pair1@test.com",
            first_name="Alice",
            last_name="Partner",
            membership_status="Full Member",
        )
        self.pair_member2 = Member.objects.create(
            username="pair2",
            email="pair2@test.com",
            first_name="Bob",
            last_name="Buddy",
            membership_status="Full Member",
        )
        self.avoid_member = Member.objects.create(
            username="avoid1",
            email="avoid1@test.com",
            first_name="Charlie",
            last_name="Conflict",
            membership_status="Full Member",
        )

    def test_pairing_preferences_display_without_preferences(self):
        """Page loads without errors when no pairing preferences are set."""
        self.client.login(username="testmember", password="testpass123")
        url = reverse("duty_roster:blackout_manage")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        # Should not show "Currently selected" when no preferences set
        self.assertNotContains(response, "Currently selected:")

    def test_pairing_preferences_display_with_pair_with(self):
        """Page shows saved 'prefer to work with' members as badges."""
        from duty_roster.models import DutyPairing

        # Set up pairing preferences
        DutyPairing.objects.create(member=self.member, pair_with=self.pair_member1)
        DutyPairing.objects.create(member=self.member, pair_with=self.pair_member2)

        self.client.login(username="testmember", password="testpass123")
        url = reverse("duty_roster:blackout_manage")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        # Should show "Currently selected" text
        self.assertContains(response, "Currently selected:")
        # Should show both paired members' names
        self.assertContains(response, "Alice Partner")
        self.assertContains(response, "Bob Buddy")
        # Should have success styling (green badges)
        self.assertContains(response, "bg-success-subtle")

    def test_pairing_preferences_display_with_avoid_with(self):
        """Page shows saved 'avoid scheduling with' members as badges."""
        from duty_roster.models import DutyAvoidance

        # Set up avoidance preferences
        DutyAvoidance.objects.create(member=self.member, avoid_with=self.avoid_member)

        self.client.login(username="testmember", password="testpass123")
        url = reverse("duty_roster:blackout_manage")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        # Should show "Currently selected" text
        self.assertContains(response, "Currently selected:")
        # Should show avoided member's name
        self.assertContains(response, "Charlie Conflict")
        # Should have warning styling (orange/yellow badges)
        self.assertContains(response, "bg-warning-subtle")

    def test_pairing_preferences_display_with_both(self):
        """Page shows both pair_with and avoid_with preferences."""
        from duty_roster.models import DutyAvoidance, DutyPairing

        # Set up both types of preferences
        DutyPairing.objects.create(member=self.member, pair_with=self.pair_member1)
        DutyAvoidance.objects.create(member=self.member, avoid_with=self.avoid_member)

        self.client.login(username="testmember", password="testpass123")
        url = reverse("duty_roster:blackout_manage")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        # Should show both members
        self.assertContains(response, "Alice Partner")
        self.assertContains(response, "Charlie Conflict")
        # Should have both badge styles
        self.assertContains(response, "bg-success-subtle")
        self.assertContains(response, "bg-warning-subtle")

    def test_post_saves_pairing_preferences_and_rehydrates_selected_options(self):
        """Saving pairing preferences should persist badges and selected options."""
        from duty_roster.models import DutyAvoidance, DutyPairing

        self.client.login(username="testmember", password="testpass123")
        url = reverse("duty_roster:blackout_manage")

        form_data = {
            "preferred_day": "",
            "dont_schedule": "",
            "scheduling_suspended": "",
            "suspended_reason": "",
            "comment": "",
            "instructor_percent": "0",
            "duty_officer_percent": "0",
            "ado_percent": "0",
            "towpilot_percent": "0",
            "max_assignments_per_month": "2.00",
            "allow_weekend_double": "",
            "pair_with": [str(self.pair_member1.id), str(self.pair_member2.id)],
            "avoid_with": [str(self.avoid_member.id)],
        }

        response = self.client.post(url, data=form_data, follow=True)

        self.assertEqual(response.status_code, 200)

        pair_ids = set(
            DutyPairing.objects.filter(member=self.member).values_list(
                "pair_with_id", flat=True
            )
        )
        avoid_ids = set(
            DutyAvoidance.objects.filter(member=self.member).values_list(
                "avoid_with_id", flat=True
            )
        )

        self.assertEqual(pair_ids, {self.pair_member1.id, self.pair_member2.id})
        self.assertEqual(avoid_ids, {self.avoid_member.id})

        self.assertContains(response, "Duty preferences saved successfully")
        self.assertContains(response, "Alice Partner")
        self.assertContains(response, "Bob Buddy")
        self.assertContains(response, "Charlie Conflict")

        self.assertContains(response, f'value="{self.pair_member1.id}" selected')
        self.assertContains(response, f'value="{self.pair_member2.id}" selected')
        self.assertContains(response, f'value="{self.avoid_member.id}" selected')


class BlackoutRoleChoiceSiteConfigTests(TestCase):
    """Tests for SiteConfiguration-gated role choices on blackout preferences."""

    def setUp(self):
        self.member = Member.objects.create(
            username="blackoutroles",
            email="blackoutroles@test.com",
            first_name="Blackout",
            last_name="Roles",
            membership_status="Full Member",
            instructor=True,
            duty_officer=True,
            assistant_duty_officer=True,
            towpilot=True,
            glider_rating="commercial",
        )

        self.config = SiteConfiguration.objects.create(
            club_name="Test Club",
            domain_name="test.org",
            club_abbreviation="TC",
            schedule_instructors=True,
            schedule_tow_pilots=True,
            schedule_duty_officers=True,
            schedule_assistant_duty_officers=True,
            schedule_commercial_pilots=True,
        )

    def _get_role_keys(self):
        self.client.force_login(self.member)
        response = self.client.get(reverse("duty_roster:blackout_manage"))
        self.assertEqual(response.status_code, 200)
        return {role for role, _label in response.context["role_percent_choices"]}

    def test_hides_all_role_choices_when_all_schedule_flags_false(self):
        self.config.schedule_instructors = False
        self.config.schedule_tow_pilots = False
        self.config.schedule_duty_officers = False
        self.config.schedule_assistant_duty_officers = False
        self.config.schedule_commercial_pilots = False
        self.config.save()

        self.assertEqual(self._get_role_keys(), set())

    def test_shows_only_enabled_role_choices_for_qualified_member(self):
        self.config.schedule_instructors = True
        self.config.schedule_tow_pilots = False
        self.config.schedule_duty_officers = True
        self.config.schedule_assistant_duty_officers = False
        self.config.schedule_commercial_pilots = False
        self.config.save()

        role_keys = self._get_role_keys()
        self.assertEqual(role_keys, {"instructor", "duty_officer"})

    def test_hides_commercial_role_when_commercial_scheduling_disabled(self):
        self.config.schedule_commercial_pilots = False
        self.config.save()

        role_keys = self._get_role_keys()
        self.assertNotIn("commercial_pilot", role_keys)
        self.assertIn("instructor", role_keys)

    def test_post_saves_preferences_when_some_qualified_roles_are_hidden(self):
        self.config.schedule_instructors = True
        self.config.schedule_tow_pilots = False
        self.config.schedule_duty_officers = False
        self.config.schedule_assistant_duty_officers = False
        self.config.schedule_commercial_pilots = False
        self.config.save()

        self.client.force_login(self.member)
        response = self.client.post(
            reverse("duty_roster:blackout_manage"),
            data={
                "preferred_day": "",
                "dont_schedule": "",
                "scheduling_suspended": "",
                "suspended_reason": "",
                "comment": "",
                "instructor_percent": "100",
                "max_assignments_per_month": "4",
                "allow_weekend_double": "",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        pref = DutyPreference.objects.get(member=self.member)
        self.assertEqual(pref.instructor_percent, 100)
        self.assertEqual(pref.commercial_pilot_percent, 0)
        self.assertEqual(pref.towpilot_percent, 0)
        self.assertContains(response, "Duty preferences saved successfully")

    def test_single_role_member_disabled_by_config_stays_zero_percent(self):
        commercial_only_member = Member.objects.create(
            username="commercialonly",
            email="commercialonly@test.com",
            first_name="Commercial",
            last_name="Only",
            membership_status="Full Member",
            glider_rating="commercial",
            instructor=False,
            duty_officer=False,
            assistant_duty_officer=False,
            towpilot=False,
        )

        self.config.schedule_instructors = False
        self.config.schedule_tow_pilots = False
        self.config.schedule_duty_officers = False
        self.config.schedule_assistant_duty_officers = False
        self.config.schedule_commercial_pilots = False
        self.config.save()

        self.client.force_login(commercial_only_member)
        response = self.client.post(
            reverse("duty_roster:blackout_manage"),
            data={
                "preferred_day": "",
                "dont_schedule": "",
                "scheduling_suspended": "",
                "suspended_reason": "",
                "comment": "",
                "max_assignments_per_month": "4",
                "allow_weekend_double": "",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        pref = DutyPreference.objects.get(member=commercial_only_member)
        self.assertEqual(pref.commercial_pilot_percent, 0)
        self.assertEqual(pref.instructor_percent, 0)
        self.assertContains(response, "Duty preferences saved successfully")

    def test_post_crafted_hidden_role_percent_is_forced_to_zero(self):
        self.config.schedule_instructors = True
        self.config.schedule_tow_pilots = False
        self.config.schedule_duty_officers = True
        self.config.schedule_assistant_duty_officers = False
        self.config.schedule_commercial_pilots = False
        self.config.save()

        self.client.force_login(self.member)
        response = self.client.post(
            reverse("duty_roster:blackout_manage"),
            data={
                "preferred_day": "",
                "dont_schedule": "",
                "scheduling_suspended": "",
                "suspended_reason": "",
                "comment": "",
                "instructor_percent": "0",
                "duty_officer_percent": "0",
                "towpilot_percent": "100",
                "max_assignments_per_month": "4",
                "allow_weekend_double": "",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        pref = DutyPreference.objects.get(member=self.member)
        self.assertEqual(pref.towpilot_percent, 0)
        self.assertEqual(pref.instructor_percent, 0)
        self.assertEqual(pref.duty_officer_percent, 0)
        self.assertContains(response, "Duty preferences saved successfully")

    def test_post_crafted_unqualified_role_percent_is_forced_to_zero(self):
        instructor_only_member = Member.objects.create(
            username="instructoronly",
            email="instructoronly@test.com",
            first_name="Instructor",
            last_name="Only",
            membership_status="Full Member",
            instructor=True,
            towpilot=True,
            duty_officer=False,
            assistant_duty_officer=False,
            glider_rating="none",
        )

        self.config.schedule_instructors = True
        self.config.schedule_tow_pilots = True
        self.config.schedule_duty_officers = True
        self.config.schedule_assistant_duty_officers = True
        self.config.schedule_commercial_pilots = True
        self.config.save()

        self.client.force_login(instructor_only_member)
        response = self.client.post(
            reverse("duty_roster:blackout_manage"),
            data={
                "preferred_day": "",
                "dont_schedule": "",
                "scheduling_suspended": "",
                "suspended_reason": "",
                "comment": "",
                "instructor_percent": "0",
                "towpilot_percent": "0",
                "duty_officer_percent": "100",
                "max_assignments_per_month": "4",
                "allow_weekend_double": "",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        pref = DutyPreference.objects.get(member=instructor_only_member)
        self.assertEqual(pref.duty_officer_percent, 0)
        self.assertEqual(pref.instructor_percent, 0)
        self.assertEqual(pref.towpilot_percent, 0)
        self.assertContains(response, "Duty preferences saved successfully")

    def test_dynamic_roles_enable_choices_even_when_legacy_schedule_flags_disabled(
        self,
    ):
        self.config.schedule_instructors = False
        self.config.schedule_tow_pilots = False
        self.config.schedule_duty_officers = False
        self.config.schedule_assistant_duty_officers = False
        self.config.schedule_commercial_pilots = False
        self.config.enable_dynamic_duty_roles = True
        self.config.save()

        DutyRoleDefinition.objects.create(
            site_configuration=self.config,
            key="am_tow",
            display_name="AM Tow",
            legacy_role_key="towpilot",
            is_active=True,
            sort_order=10,
        )
        DutyRoleDefinition.objects.create(
            site_configuration=self.config,
            key="pm_tow",
            display_name="PM Tow",
            legacy_role_key="towpilot",
            is_active=True,
            sort_order=20,
        )
        DutyRoleDefinition.objects.create(
            site_configuration=self.config,
            key="am_instructor",
            display_name="AM Instructor",
            legacy_role_key="instructor",
            is_active=True,
            sort_order=30,
        )

        self.client.force_login(self.member)
        response = self.client.get(reverse("duty_roster:blackout_manage"))
        self.assertEqual(response.status_code, 200)

        role_choices = dict(response.context["role_percent_choices"])
        self.assertIn("towpilot", role_choices)
        self.assertIn("instructor", role_choices)
        self.assertIn("AM Tow", role_choices["towpilot"])
        self.assertIn("PM Tow", role_choices["towpilot"])
        self.assertIn("AM Instructor", role_choices["instructor"])

    def test_dynamic_mode_hides_commercial_when_not_configured(self):
        self.config.enable_dynamic_duty_roles = True
        self.config.schedule_commercial_pilots = True
        self.config.schedule_instructors = True
        self.config.save()

        DutyRoleDefinition.objects.create(
            site_configuration=self.config,
            key="am_instructor",
            display_name="AM Instructor",
            legacy_role_key="instructor",
            is_active=True,
            sort_order=10,
        )

        self.client.force_login(self.member)
        response = self.client.get(reverse("duty_roster:blackout_manage"))
        self.assertEqual(response.status_code, 200)

        role_keys = {role for role, _label in response.context["role_percent_choices"]}
        self.assertIn("instructor", role_keys)
        self.assertNotIn("commercial_pilot", role_keys)
