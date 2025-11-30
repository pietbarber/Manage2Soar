from datetime import date, time, timedelta

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from duty_roster.models import DutyDay, DutyPreference, DutySlot, MemberBlackout
from duty_roster.views import (
    _calculate_membership_duration,
    _has_performed_duty_detailed,
    calendar_refresh_response,
)
from logsheet.models import Airfield, Flight, Glider, Logsheet
from members.models import Member

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

    def test_member_with_recent_duty_not_in_report(self):
        """Member who has done recent duty should not appear"""
        # Give delinquent member a recent duty assignment
        duty_day = DutyDay.objects.create(date=date.today() - timedelta(days=30))
        DutySlot.objects.create(
            duty_day=duty_day, member=self.delinquent_member, role="instructor"
        )

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

    def test_has_performed_duty_detailed_with_duty_slot(self):
        """Test helper function when member has recent duty slot"""
        duty_date = date.today() - timedelta(days=30)
        duty_day = DutyDay.objects.create(date=duty_date)
        DutySlot.objects.create(
            duty_day=duty_day, member=self.member, role="instructor"
        )

        cutoff_date = date.today() - timedelta(days=365)
        result = _has_performed_duty_detailed(self.member, cutoff_date)

        self.assertTrue(result["has_duty"])
        self.assertEqual(result["last_duty_date"], duty_date)
        self.assertEqual(result["last_duty_role"], "Instructor (Scheduled Only)")
        self.assertEqual(result["last_duty_type"], "DutySlot - Scheduled")

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
