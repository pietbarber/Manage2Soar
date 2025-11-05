
from datetime import date, timedelta, time
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model

from members.models import Member
from logsheet.models import Logsheet, Glider, Flight, Airfield
from duty_roster.models import DutySlot, DutyDay, MemberBlackout, DutyPreference
from duty_roster.views import _has_performed_duty_detailed, _calculate_membership_duration, calendar_refresh_response

User = get_user_model()


class DutyDelinquentsDetailViewTests(TestCase):
    def setUp(self):
        """Set up test data"""
        self.client = Client()

        # Create test airfield
        self.airfield = Airfield.objects.create(
            name="Test Field",
            identifier="TEST"
        )

        # Create test glider
        self.glider = Glider.objects.create(
            make="Test",
            model="Glider",
            n_number="N12345",
            competition_number="ABC"
        )

        # Create members with different permission levels
        self.regular_member = Member.objects.create(
            username="regular",
            email="regular@test.com",
            first_name="Regular",
            last_name="Member",
            membership_status="Full Member",
            joined_club=date.today() - timedelta(days=365)
        )

        self.rostermeister = Member.objects.create(
            username="rostermeister",
            email="roster@test.com",
            first_name="Roster",
            last_name="Meister",
            membership_status="Full Member",
            rostermeister=True,
            joined_club=date.today() - timedelta(days=365)
        )

        self.member_manager = Member.objects.create(
            username="membermanager",
            email="member@test.com",
            first_name="Member",
            last_name="Manager",
            membership_status="Full Member",
            member_manager=True,
            joined_club=date.today() - timedelta(days=365)
        )

        self.director = Member.objects.create(
            username="director",
            email="director@test.com",
            first_name="Director",
            last_name="Person",
            membership_status="Full Member",
            director=True,
            joined_club=date.today() - timedelta(days=365)
        )

        self.superuser = Member.objects.create(
            username="superuser",
            email="super@test.com",
            first_name="Super",
            last_name="User",
            membership_status="Full Member",
            is_superuser=True,
            joined_club=date.today() - timedelta(days=365)
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
            joined_club=date.today() - timedelta(days=365)
        )

        # Create recent flights for delinquent member
        for i in range(5):
            flight_date = date.today() - timedelta(days=30 * i)
            logsheet = Logsheet.objects.create(
                log_date=flight_date,
                airfield=self.airfield,
                created_by=self.delinquent_member,
                finalized=True
            )
            Flight.objects.create(
                pilot=self.delinquent_member,
                glider=self.glider,
                logsheet=logsheet,
                launch_time=time(10, 0, 0),
                landing_time=time(11, 0, 0)
            )

    def test_permission_required_regular_member(self):
        """Regular members should not have access"""
        self.client.force_login(self.regular_member)
        response = self.client.get(reverse('duty_roster:duty_delinquents_detail'))
        # Should redirect to login or show permission denied
        self.assertNotEqual(response.status_code, 200)

    def test_permission_allowed_rostermeister(self):
        """Rostermeister should have access"""
        self.client.force_login(self.rostermeister)
        response = self.client.get(reverse('duty_roster:duty_delinquents_detail'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Duty Delinquents Detail Report")

    def test_permission_allowed_member_manager(self):
        """Member manager should have access"""
        self.client.force_login(self.member_manager)
        response = self.client.get(reverse('duty_roster:duty_delinquents_detail'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Duty Delinquents Detail Report")

    def test_permission_allowed_director(self):
        """Director should have access"""
        self.client.force_login(self.director)
        response = self.client.get(reverse('duty_roster:duty_delinquents_detail'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Duty Delinquents Detail Report")

    def test_permission_allowed_superuser(self):
        """Superuser should have access"""
        self.client.force_login(self.superuser)
        response = self.client.get(reverse('duty_roster:duty_delinquents_detail'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Duty Delinquents Detail Report")

    def test_delinquent_member_appears_in_report(self):
        """Delinquent member should appear in the report"""
        self.client.force_login(self.rostermeister)
        response = self.client.get(reverse('duty_roster:duty_delinquents_detail'))

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
            duty_day=duty_day,
            member=self.delinquent_member,
            role="instructor"
        )

        self.client.force_login(self.rostermeister)
        response = self.client.get(reverse('duty_roster:duty_delinquents_detail'))

        self.assertEqual(response.status_code, 200)
        # Should not contain the delinquent member anymore
        self.assertNotContains(response, self.delinquent_member.full_display_name)

    def test_inactive_member_not_in_report(self):
        """Inactive members should be excluded"""
        self.delinquent_member.membership_status = "Inactive"
        self.delinquent_member.save()

        self.client.force_login(self.rostermeister)
        response = self.client.get(reverse('duty_roster:duty_delinquents_detail'))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.delinquent_member.full_display_name)

    def test_member_blackouts_display(self):
        """Member blackouts should be displayed"""
        # Add current and recent blackouts
        MemberBlackout.objects.create(
            member=self.delinquent_member,
            date=date.today() + timedelta(days=30),
            note="Vacation planned"
        )
        MemberBlackout.objects.create(
            member=self.delinquent_member,
            date=date.today() - timedelta(days=60),
            note="Was traveling"
        )

        self.client.force_login(self.rostermeister)
        response = self.client.get(reverse('duty_roster:duty_delinquents_detail'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Vacation planned")
        self.assertContains(response, "Was traveling")

    def test_suspended_member_indication(self):
        """Suspended members should show suspension status"""
        DutyPreference.objects.create(
            member=self.delinquent_member,
            scheduling_suspended=True,
            suspended_reason="Medical issue"
        )

        self.client.force_login(self.rostermeister)
        response = self.client.get(reverse('duty_roster:duty_delinquents_detail'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Scheduling Suspended")
        self.assertContains(response, "Medical issue")

    def test_no_delinquents_message(self):
        """Should show success message when no delinquents found"""
        # Remove flights from delinquent member
        Flight.objects.filter(pilot=self.delinquent_member).delete()

        self.client.force_login(self.rostermeister)
        response = self.client.get(reverse('duty_roster:duty_delinquents_detail'))

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
            joined_club=date.today() - timedelta(days=365)
        )

    def test_has_performed_duty_detailed_no_duty(self):
        """Test helper function when member has no duty"""
        cutoff_date = date.today() - timedelta(days=365)
        result = _has_performed_duty_detailed(self.member, cutoff_date)

        self.assertFalse(result['has_duty'])
        self.assertIsNone(result['last_duty_date'])
        self.assertIsNone(result['last_duty_role'])

    def test_has_performed_duty_detailed_with_duty_slot(self):
        """Test helper function when member has recent duty slot"""
        duty_date = date.today() - timedelta(days=30)
        duty_day = DutyDay.objects.create(date=duty_date)
        DutySlot.objects.create(
            duty_day=duty_day,
            member=self.member,
            role="instructor"
        )

        cutoff_date = date.today() - timedelta(days=365)
        result = _has_performed_duty_detailed(self.member, cutoff_date)

        self.assertTrue(result['has_duty'])
        self.assertEqual(result['last_duty_date'], duty_date)
        self.assertEqual(result['last_duty_role'], "Instructor (Scheduled Only)")
        self.assertEqual(result['last_duty_type'], "DutySlot - Scheduled")

    def test_has_performed_duty_detailed_with_instruction_flight(self):
        """Test helper function when member has performed actual instruction"""
        from logsheet.models import Logsheet, Glider, Flight, Airfield

        # Create test data
        airfield = Airfield.objects.create(name="Test Field", identifier="TEST")
        glider = Glider.objects.create(make="Test", model="Glider", n_number="N12345")

        flight_date = date.today() - timedelta(days=30)
        logsheet = Logsheet.objects.create(
            log_date=flight_date,
            airfield=airfield,
            created_by=self.member,
            finalized=True
        )

        # Create flight where member was instructor
        Flight.objects.create(
            pilot=self.member,  # Different member as pilot
            instructor=self.member,  # Our test member as instructor
            glider=glider,
            logsheet=logsheet,
            launch_time=time(10, 0, 0),
            landing_time=time(11, 0, 0)
        )

        cutoff_date = date.today() - timedelta(days=365)
        result = _has_performed_duty_detailed(self.member, cutoff_date)

        self.assertTrue(result['has_duty'])
        self.assertEqual(result['last_duty_date'], flight_date)
        self.assertEqual(result['last_duty_role'], "Instructor (Flight)")
        self.assertEqual(result['last_duty_type'], "Flight Activity")
        self.assertEqual(result['flight_count'], 1)

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
        self.assertIn('HX-Trigger', response.headers)

        # Parse the HX-Trigger JSON
        import json
        trigger_data = json.loads(response.headers['HX-Trigger'])

        # Verify structure and values
        self.assertIn('refreshCalendar', trigger_data)
        self.assertEqual(trigger_data['refreshCalendar']['year'], 2024)
        self.assertEqual(trigger_data['refreshCalendar']['month'], 12)

    def test_calendar_refresh_response_json_format(self):
        """Test that the JSON structure is correct"""
        year, month = 2025, 1
        response = calendar_refresh_response(year, month)

        import json
        trigger_data = json.loads(response.headers['HX-Trigger'])

        # Verify the exact expected structure
        expected_structure = {
            'refreshCalendar': {
                'year': 2025,
                'month': 1
            }
        }
        self.assertEqual(trigger_data, expected_structure)

    def test_calendar_refresh_response_type_conversion(self):
        """Test that string year/month are converted to integers"""
        year, month = "2023", "11"  # Pass as strings
        response = calendar_refresh_response(year, month)

        import json
        trigger_data = json.loads(response.headers['HX-Trigger'])

        # Should be converted to integers
        self.assertEqual(trigger_data['refreshCalendar']['year'], 2023)
        self.assertEqual(trigger_data['refreshCalendar']['month'], 11)
        self.assertIsInstance(trigger_data['refreshCalendar']['year'], int)
        self.assertIsInstance(trigger_data['refreshCalendar']['month'], int)
