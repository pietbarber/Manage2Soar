"""
Tests for the membership application system.
"""

import pytest
from django.test import Client, TestCase
from django.urls import reverse

from members.forms_applications import MembershipApplicationForm
from members.models import Member
from members.models_applications import MembershipApplication


@pytest.mark.django_db
class MembershipApplicationModelTests:
    """Test the MembershipApplication model functionality."""

    def test_create_application(self):
        """Test creating a basic membership application."""
        app = MembershipApplication.objects.create(
            first_name="John",
            last_name="Doe",
            email="john.doe@example.com",
            phone="555-123-4567",
            address_line1="123 Main St",
            city="Anytown",
            state="CA",
            zip_code="12345",
            emergency_contact_name="Jane Doe",
            emergency_contact_relationship="Spouse",
            emergency_contact_phone="555-987-6543",
            soaring_goals="I want to learn to fly gliders",
            agrees_to_terms=True,
            agrees_to_safety_rules=True,
            agrees_to_financial_obligations=True,
        )

        assert app.application_id is not None
        assert app.status == "pending"
        assert app.full_name == "John Doe"
        assert str(app) == "John Doe - Pending Review"

    def test_full_name_with_middle_initial(self):
        """Test full name property with middle initial."""
        app = MembershipApplication(
            first_name="John",
            middle_initial="Q",
            last_name="Doe",
        )
        assert app.full_name == "John Q. Doe"

    def test_full_name_with_suffix(self):
        """Test full name property with suffix."""
        app = MembershipApplication(
            first_name="John",
            last_name="Doe",
            name_suffix="Jr.",
        )
        assert app.full_name == "John Doe Jr."

    def test_can_be_approved_missing_required_fields(self):
        """Test can_be_approved returns False for missing required fields."""
        app = MembershipApplication()
        assert not app.can_be_approved()

    def test_can_be_approved_missing_agreements(self):
        """Test can_be_approved returns False without agreements."""
        app = MembershipApplication(
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            phone="555-123-4567",
            address_line1="123 Main St",
            city="Anytown",
            state="CA",
            zip_code="12345",
            emergency_contact_name="Jane Doe",
            emergency_contact_phone="555-987-6543",
            # Missing agreements
        )
        assert not app.can_be_approved()

    def test_can_be_approved_valid_application(self):
        """Test can_be_approved returns True for complete application."""
        app = MembershipApplication(
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            phone="555-123-4567",
            address_line1="123 Main St",
            city="Anytown",
            state="CA",
            zip_code="12345",
            emergency_contact_name="Jane Doe",
            emergency_contact_phone="555-987-6543",
            agrees_to_terms=True,
            agrees_to_safety_rules=True,
            agrees_to_financial_obligations=True,
        )
        assert app.can_be_approved()

    def test_approve_application_creates_member(self):
        """Test that approving an application creates a member account."""
        app = MembershipApplication.objects.create(
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            phone="555-123-4567",
            address_line1="123 Main St",
            city="Anytown",
            state="CA",
            zip_code="12345",
            emergency_contact_name="Jane Doe",
            emergency_contact_relationship="Spouse",
            emergency_contact_phone="555-987-6543",
            soaring_goals="I want to learn to fly gliders",
            agrees_to_terms=True,
            agrees_to_safety_rules=True,
            agrees_to_financial_obligations=True,
        )

        member = app.approve_application()

        assert member is not None
        assert member.username == "john.doe"  # generate_username("John", "Doe")
        assert member.email == "john@example.com"
        assert member.first_name == "John"
        assert member.last_name == "Doe"
        assert member.phone == "555-123-4567"

        # Check application status updated
        app.refresh_from_db()
        assert app.status == "approved"
        assert app.member_account == member

    def test_add_to_waitlist(self):
        """Test adding an application to the waitlist."""
        app = MembershipApplication.objects.create(
            first_name="Jane",
            last_name="Smith",
            email="jane@example.com",
            phone="555-123-4567",
            address_line1="456 Oak St",
            city="Anytown",
            state="CA",
            zip_code="12345",
            emergency_contact_name="John Smith",
            emergency_contact_relationship="Spouse",
            emergency_contact_phone="555-987-6543",
            soaring_goals="I want to soar",
            agrees_to_terms=True,
            agrees_to_safety_rules=True,
            agrees_to_financial_obligations=True,
        )

        app.add_to_waitlist()

        app.refresh_from_db()
        assert app.status == "waitlisted"
        assert app.waitlist_position == 1

    def test_add_to_waitlist_already_waitlisted(self):
        """Test that adding an already-waitlisted application doesn't change position.

        This prevents the bug where clicking 'Add to Waitlist' on someone already
        on the waitlist would assign them a new position (causing gaps).
        """
        # Create first waitlisted application
        app1 = MembershipApplication.objects.create(
            first_name="First",
            last_name="Person",
            email="first@example.com",
            phone="555-123-4567",
            address_line1="123 Main St",
            city="Anytown",
            state="CA",
            zip_code="12345",
            emergency_contact_name="Contact",
            emergency_contact_relationship="Friend",
            emergency_contact_phone="555-987-6543",
            soaring_goals="Test",
            agrees_to_terms=True,
            agrees_to_safety_rules=True,
            agrees_to_financial_obligations=True,
        )
        app1.add_to_waitlist()
        assert app1.waitlist_position == 1

        # Create second waitlisted application
        app2 = MembershipApplication.objects.create(
            first_name="Second",
            last_name="Person",
            email="second@example.com",
            phone="555-123-4567",
            address_line1="456 Oak St",
            city="Anytown",
            state="CA",
            zip_code="12345",
            emergency_contact_name="Contact",
            emergency_contact_relationship="Friend",
            emergency_contact_phone="555-987-6543",
            soaring_goals="Test",
            agrees_to_terms=True,
            agrees_to_safety_rules=True,
            agrees_to_financial_obligations=True,
        )
        app2.add_to_waitlist()
        assert app2.waitlist_position == 2

        # Try to add app1 to waitlist again - should not change position
        original_position = app1.waitlist_position
        app1.add_to_waitlist()
        app1.refresh_from_db()
        assert app1.waitlist_position == original_position  # Still position 1
        assert app1.status == "waitlisted"

        # Verify app2 still at position 2 (no gaps created)
        app2.refresh_from_db()
        assert app2.waitlist_position == 2

    def test_reject_application(self):
        """Test rejecting an application."""
        app = MembershipApplication.objects.create(
            first_name="Bob",
            last_name="Jones",
            email="bob@example.com",
            phone="555-123-4567",
            address_line1="789 Pine St",
            city="Anytown",
            state="CA",
            zip_code="12345",
            emergency_contact_name="Sue Jones",
            emergency_contact_relationship="Spouse",
            emergency_contact_phone="555-987-6543",
            soaring_goals="I want to fly",
            agrees_to_terms=True,
            agrees_to_safety_rules=True,
            agrees_to_financial_obligations=True,
        )

        app.reject_application()

        app.refresh_from_db()
        assert app.status == "rejected"


@pytest.mark.django_db
class MembershipApplicationFormTests:
    """Test the membership application form."""

    def test_valid_form(self):
        """Test form validation with valid data."""
        form_data = {
            "first_name": "John",
            "last_name": "Doe",
            "email": "john@example.com",
            "phone": "555-123-4567",
            "address_line1": "123 Main St",
            "city": "Anytown",
            "state": "CA",
            "zip_code": "12345",
            "emergency_contact_name": "Jane Doe",
            "emergency_contact_relationship": "Spouse",
            "emergency_contact_phone": "555-987-6543",
            "soaring_goals": "I want to learn gliding",
            "agrees_to_terms": True,
            "agrees_to_safety_rules": True,
            "agrees_to_financial_obligations": True,
        }

        form = MembershipApplicationForm(data=form_data)
        assert form.is_valid()

    def test_missing_required_fields(self):
        """Test form validation with missing required fields."""
        form_data = {
            "first_name": "John",
            # Missing last_name and other required fields
        }

        form = MembershipApplicationForm(data=form_data)
        assert not form.is_valid()
        assert "last_name" in form.errors

    def test_invalid_email(self):
        """Test form validation with invalid email."""
        form_data = {
            "first_name": "John",
            "last_name": "Doe",
            "email": "invalid-email",
            "phone": "555-123-4567",
            "address_line1": "123 Main St",
            "city": "Anytown",
            "state": "CA",
            "zip_code": "12345",
            "emergency_contact_name": "Jane Doe",
            "emergency_contact_relationship": "Spouse",
            "emergency_contact_phone": "555-987-6543",
            "soaring_goals": "I want to learn gliding",
            "agrees_to_terms": True,
            "agrees_to_safety_rules": True,
            "agrees_to_financial_obligations": True,
        }

        form = MembershipApplicationForm(data=form_data)
        assert not form.is_valid()
        assert "email" in form.errors


class MembershipApplicationViewTests(TestCase):
    """Test membership application views."""

    def setUp(self):
        """Set up test fixtures."""
        self.client = Client()

        # Enable membership applications
        from siteconfig.models import SiteConfiguration

        if not SiteConfiguration.objects.exists():
            SiteConfiguration.objects.create(
                club_name="Test Club",
                club_abbreviation="TC",
                domain_name="testclub.com",
                membership_application_enabled=True,
            )

    def _create_manager(self, username="manager", email="manager@example.com"):
        """Create and return a member manager user."""
        manager = Member.objects.create_user(
            username=username,
            email=email,
            password="testpass",
            member_manager=True,
            membership_status="Full Member",
        )
        self.client.force_login(manager)
        return manager

    def _create_waitlisted_app(self, first_name, email):
        """Create and return a waitlisted application."""
        application = MembershipApplication.objects.create(
            first_name=first_name,
            last_name="Test",
            email=email,
            phone="555-123-4567",
            address_line1="123 Main St",
            city="Anytown",
            state="CA",
            zip_code="12345",
            emergency_contact_name="Contact Person",
            emergency_contact_relationship="Friend",
            emergency_contact_phone="555-987-6543",
            soaring_goals="Test",
            agrees_to_terms=True,
            agrees_to_safety_rules=True,
            agrees_to_financial_obligations=True,
        )
        application.add_to_waitlist()
        return application

    def test_application_form_get(self):
        """Test GET request to application form."""
        response = self.client.get(
            reverse("members:membership_application"), follow=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Membership Application")

    def test_application_form_post_valid(self):
        """Test POST request with valid application data."""
        form_data = {
            "first_name": "John",
            "last_name": "Doe",
            "email": "john@example.com",
            "phone": "555-123-4567",
            "address_line1": "123 Main St",
            "city": "Anytown",
            "state": "CA",
            "zip_code": "12345",
            "country": "USA",
            "emergency_contact_name": "Jane Doe",
            "emergency_contact_relationship": "Spouse",
            "emergency_contact_phone": "555-987-6543",
            "soaring_goals": "I want to learn gliding",
            "glider_rating": "none",
            "total_flight_hours": 0,
            "glider_flight_hours": 0,
            "recent_flight_hours": 0,
            "agrees_to_terms": True,
            "agrees_to_safety_rules": True,
            "agrees_to_financial_obligations": True,
        }

        # Test form validation directly first
        from members.forms_applications import MembershipApplicationForm

        form = MembershipApplicationForm(data=form_data)
        if not form.is_valid():
            print(f"Form errors: {form.errors}")
            for field, errors in form.errors.items():
                print(f"Field {field}: {errors}")

        response = self.client.post(
            reverse("members:membership_application"), form_data, follow=True
        )
        print(f"Response status: {response.status_code}")

        # Check if any applications were created
        apps = MembershipApplication.objects.all()
        print(f"Applications created: {apps.count()}")
        for app in apps:
            print(f"App: {app.email} - {app.first_name} {app.last_name}")

        self.assertEqual(response.status_code, 200)  # Success page

        # Check application was created
        if apps.count() > 0:
            app = MembershipApplication.objects.get(email="john@example.com")
            self.assertEqual(app.first_name, "John")
            self.assertEqual(app.status, "pending")
        else:
            self.fail("No applications were created")

    def test_application_form_post_invalid(self):
        """Test POST request with invalid data."""
        form_data = {
            "first_name": "John",
            # Missing required fields
        }

        response = self.client.post(
            reverse("members:membership_application"), form_data, follow=True
        )
        self.assertEqual(response.status_code, 200)  # Form re-rendered with errors
        self.assertContains(response, "This field is required")

    def test_multiple_validation_errors_shown_together(self):
        """Test that multiple validation errors are shown at once, not one at a time.

        This is a regression test for issue #303 where form errors appeared one
        at a time instead of all together.
        """
        form_data = {
            "first_name": "John",
            "last_name": "Doe",
            "email": "john@example.com",
            "phone": "555-123-4567",
            "address_line1": "123 Main St",
            "city": "Anytown",
            "state": "CA",
            "zip_code": "12345",
            "emergency_contact_name": "Jane Doe",
            "emergency_contact_relationship": "Spouse",
            "emergency_contact_phone": "555-987-6543",
            "soaring_goals": "I want to learn gliding",
            # Intentionally omit all three agreement checkboxes
            "agrees_to_terms": False,
            "agrees_to_safety_rules": False,
            "agrees_to_financial_obligations": False,
        }

        form = MembershipApplicationForm(data=form_data)
        self.assertFalse(form.is_valid())

        # All three errors should be present at once
        self.assertIn("agrees_to_terms", form.errors)
        self.assertIn("agrees_to_safety_rules", form.errors)
        self.assertIn("agrees_to_financial_obligations", form.errors)

    def test_conditional_field_errors_shown_together(self):
        """Test that multiple conditional field errors are shown at once.

        This is a regression test for issue #303. When checkboxes for insurance
        rejection, club rejection, and aviation incidents are checked but the
        detail fields are left empty, all errors should appear together.
        """
        form_data = {
            "first_name": "John",
            "last_name": "Doe",
            "email": "john@example.com",
            "phone": "555-123-4567",
            "address_line1": "123 Main St",
            "city": "Anytown",
            "state": "CA",
            "zip_code": "12345",
            "emergency_contact_name": "Jane Doe",
            "emergency_contact_relationship": "Spouse",
            "emergency_contact_phone": "555-987-6543",
            "soaring_goals": "I want to learn gliding",
            "agrees_to_terms": True,
            "agrees_to_safety_rules": True,
            "agrees_to_financial_obligations": True,
            # Check all three conditional checkboxes but leave details empty
            "insurance_rejection_history": True,
            "insurance_rejection_details": "",
            "club_rejection_history": True,
            "club_rejection_details": "",
            "aviation_incidents": True,
            "aviation_incident_details": "",
        }

        form = MembershipApplicationForm(data=form_data)
        self.assertFalse(form.is_valid())

        # All three conditional field errors should be present at once
        self.assertIn("insurance_rejection_details", form.errors)
        self.assertIn("club_rejection_details", form.errors)
        self.assertIn("aviation_incident_details", form.errors)

    def test_application_status_view_valid_id(self):
        """Test application status view with valid ID."""
        app = MembershipApplication.objects.create(
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            phone="555-123-4567",
            address_line1="123 Main St",
            city="Anytown",
            state="CA",
            zip_code="12345",
            emergency_contact_name="Jane Doe",
            emergency_contact_relationship="Spouse",
            emergency_contact_phone="555-987-6543",
            soaring_goals="I want to learn gliding",
            agrees_to_terms=True,
            agrees_to_safety_rules=True,
            agrees_to_financial_obligations=True,
        )

        response = self.client.get(
            reverse("members:membership_application_status", args=[app.application_id]),
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Hello John,")
        self.assertContains(response, "Pending Review")

    def test_application_status_view_invalid_id(self):
        """Test application status view with invalid ID."""
        import uuid

        response = self.client.get(
            reverse("members:membership_application_status", args=[uuid.uuid4()])
        )
        self.assertEqual(response.status_code, 404)

    def test_waitlist_view(self):
        """Test the waitlist view."""
        self._create_manager()

        # Create some waitlisted applications
        for i in range(3):
            self._create_waitlisted_app(f"Person{i}", f"person{i}@example.com")

        response = self.client.get(reverse("members:membership_waitlist"), follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Membership Waitlist")
        self.assertContains(response, "Person0 Test")
        self.assertContains(response, "Person1 Test")
        self.assertContains(response, "Person2 Test")

    def test_waitlist_move_to_top(self):
        """Test moving an applicant to the top of the waitlist."""
        self._create_manager()

        # Create waitlisted applications
        apps = []
        for i in range(5):
            app = self._create_waitlisted_app(f"Person{i}", f"person{i}@example.com")
            apps.append(app)

        # Verify initial positions
        for i, app in enumerate(apps):
            app.refresh_from_db()
            self.assertEqual(app.waitlist_position, i + 1)

        # Move Person4 (position 5) to the top
        response = self.client.post(
            reverse("members:membership_waitlist"),
            {"action": "move_to_top", "application_id": apps[4].application_id},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)

        # Verify new positions - Person4 should be at position 1
        apps[4].refresh_from_db()
        self.assertEqual(apps[4].waitlist_position, 1)

        # All others should have shifted down by 1
        for i in range(4):
            apps[i].refresh_from_db()
            self.assertEqual(apps[i].waitlist_position, i + 2)

    def test_waitlist_move_to_bottom(self):
        """Test moving an applicant to the bottom of the waitlist."""
        self._create_manager()

        # Create waitlisted applications
        apps = []
        for i in range(5):
            app = self._create_waitlisted_app(f"Person{i}", f"person{i}@example.com")
            apps.append(app)

        # Move Person0 (position 1) to the bottom
        response = self.client.post(
            reverse("members:membership_waitlist"),
            {"action": "move_to_bottom", "application_id": apps[0].application_id},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)

        # Verify new positions - Person0 should be at position 5
        apps[0].refresh_from_db()
        self.assertEqual(apps[0].waitlist_position, 5)

        # All others should have shifted up by 1
        for i in range(1, 5):
            apps[i].refresh_from_db()
            self.assertEqual(apps[i].waitlist_position, i)

    def test_waitlist_move_to_top_already_at_top(self):
        """Test moving an applicant to top when already at position 1."""
        self._create_manager()

        # Create a single waitlisted application
        application = self._create_waitlisted_app("Person0", "person0@example.com")

        # Try to move to top when already at position 1
        response = self.client.post(
            reverse("members:membership_waitlist"),
            {"action": "move_to_top", "application_id": application.application_id},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)

        # Position should remain at 1
        application.refresh_from_db()
        self.assertEqual(application.waitlist_position, 1)

        # Should show info message about already being at top
        self.assertContains(response, "already at the top")

    def test_waitlist_move_to_bottom_already_at_bottom(self):
        """Test moving an applicant to bottom when already at last position."""
        self._create_manager()

        # Create two waitlisted applications
        self._create_waitlisted_app("Person0", "person0@example.com")
        app2 = self._create_waitlisted_app("Person1", "person1@example.com")

        # Try to move app2 (position 2, the last position) to bottom
        response = self.client.post(
            reverse("members:membership_waitlist"),
            {"action": "move_to_bottom", "application_id": app2.application_id},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)

        # Position should remain at 2
        app2.refresh_from_db()
        self.assertEqual(app2.waitlist_position, 2)

        # Should show info message about already being at bottom
        self.assertContains(response, "already at the bottom")

    def test_save_notes_without_status_change(self):
        """Test that the 'Save Notes' action saves notes without changing status."""
        self._create_manager()

        # Create a pending application
        application = MembershipApplication.objects.create(
            first_name="Test",
            last_name="Applicant",
            email="test@example.com",
            phone="555-123-4567",
            address_line1="123 Main St",
            city="Anytown",
            state="CA",
            zip_code="12345",
            emergency_contact_name="Contact Person",
            emergency_contact_relationship="Friend",
            emergency_contact_phone="555-987-6543",
            soaring_goals="Test",
            agrees_to_terms=True,
            agrees_to_safety_rules=True,
            agrees_to_financial_obligations=True,
        )
        original_status = application.status

        # Save notes via the review action
        response = self.client.post(
            reverse(
                "members:membership_application_detail",
                args=[application.application_id],
            ),
            {
                "review_action": "save_notes",
                "admin_notes": "These are my private notes about this applicant.",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Notes saved successfully")

        # Verify notes were saved but status unchanged
        application.refresh_from_db()
        self.assertEqual(
            application.admin_notes, "These are my private notes about this applicant."
        )
        self.assertEqual(application.status, original_status)

    def test_add_to_waitlist_already_waitlisted_keeps_position(self):
        """Test that clicking 'Add to Waitlist' on someone already waitlisted doesn't change position.

        This regression test prevents the bug where clicking 'Add to Waitlist'
        on someone already on the waitlist would assign them a new position
        (e.g., position 3 → position 4), causing gaps in the waitlist numbering.
        """
        self._create_manager()

        # Create two waitlisted applications
        app1 = self._create_waitlisted_app("First", "first@example.com")
        app2 = self._create_waitlisted_app("Second", "second@example.com")

        self.assertEqual(app1.waitlist_position, 1)
        self.assertEqual(app2.waitlist_position, 2)

        # Try to "Add to Waitlist" again on app1 (who is already at position 1)
        response = self.client.post(
            reverse(
                "members:membership_application_detail",
                args=[app1.application_id],
            ),
            {
                "review_action": "waitlist",
                "admin_notes": "",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)

        # app1 should still be at position 1, NOT moved to position 3
        app1.refresh_from_db()
        self.assertEqual(app1.waitlist_position, 1)
        self.assertEqual(app1.status, "waitlisted")

        # app2 should still be at position 2
        app2.refresh_from_db()
        self.assertEqual(app2.waitlist_position, 2)

    def test_is_pilot_property(self):
        """Test the is_pilot property correctly identifies pilots."""
        # Non-pilot: no certificates, glider_rating='none'
        app = MembershipApplication.objects.create(
            first_name="Non",
            last_name="Pilot",
            email="nonpilot@example.com",
            phone="555-123-4567",
            address_line1="123 Main St",
            city="Anytown",
            state="CA",
            zip_code="12345",
            emergency_contact_name="Contact",
            emergency_contact_relationship="Friend",
            emergency_contact_phone="555-987-6543",
            soaring_goals="Learn to fly",
            agrees_to_terms=True,
            agrees_to_safety_rules=True,
            agrees_to_financial_obligations=True,
            has_private_pilot=False,
            has_commercial_pilot=False,
            has_cfi=False,
            glider_rating="none",
        )
        self.assertFalse(app.is_pilot)

        # Pilot with private certificate
        app.has_private_pilot = True
        app.save()
        self.assertTrue(app.is_pilot)

        # Reset and test glider rating
        app.has_private_pilot = False
        app.glider_rating = "private"
        app.save()
        self.assertTrue(app.is_pilot)

        # Test commercial pilot certificate
        app.glider_rating = "none"
        app.has_commercial_pilot = True
        app.save()
        self.assertTrue(app.is_pilot)

        # Test CFI certificate
        app.has_commercial_pilot = False
        app.has_cfi = True
        app.save()
        self.assertTrue(app.is_pilot)

        # Test student glider rating
        app.has_cfi = False
        app.glider_rating = "student"
        app.save()
        self.assertTrue(app.is_pilot)

        # Test transition glider rating
        app.glider_rating = "transition"
        app.save()
        self.assertTrue(app.is_pilot)

        # Test commercial glider rating
        app.glider_rating = "commercial"
        app.save()
        self.assertTrue(app.is_pilot)

        # Test foreign pilot rating
        app.glider_rating = "foreign"
        app.save()
        self.assertTrue(app.is_pilot)

    def test_has_soaring_experience_property(self):
        """Test the has_soaring_experience property."""
        app = MembershipApplication.objects.create(
            first_name="Test",
            last_name="Pilot",
            email="testpilot@example.com",
            phone="555-123-4567",
            address_line1="123 Main St",
            city="Anytown",
            state="CA",
            zip_code="12345",
            emergency_contact_name="Contact",
            emergency_contact_relationship="Friend",
            emergency_contact_phone="555-987-6543",
            soaring_goals="Learn to fly",
            agrees_to_terms=True,
            agrees_to_safety_rules=True,
            agrees_to_financial_obligations=True,
            glider_flight_hours=0,
        )
        self.assertFalse(app.has_soaring_experience)

        # Set some hours
        app.glider_flight_hours = 50
        app.save()
        self.assertTrue(app.has_soaring_experience)


@pytest.mark.django_db
class MembershipApplicationAdminTests:
    """Test admin functionality for membership applications."""

    def test_admin_can_view_applications(self):
        """Test that admin users can view applications."""
        # Create admin user
        admin_user = Member.objects.create_user(
            username="admin",
            email="admin@example.com",
            password="testpass",
            is_superuser=True,
            is_staff=True,
            membership_status="Full Member",
        )

        # Create application
        MembershipApplication.objects.create(
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            phone="555-123-4567",
            address_line1="123 Main St",
            city="Anytown",
            state="CA",
            zip_code="12345",
            emergency_contact_name="Jane Doe",
            emergency_contact_relationship="Spouse",
            emergency_contact_phone="555-987-6543",
            soaring_goals="I want to learn gliding",
            agrees_to_terms=True,
            agrees_to_safety_rules=True,
            agrees_to_financial_obligations=True,
        )

        client = Client()
        client.force_login(admin_user)

        response = client.get(reverse("members:membership_applications_list"))
        assert response.status_code == 200
        assert "John Doe" in response.content.decode()


@pytest.mark.django_db
class MembershipApplicationIntegrationTests:
    """Integration tests for the complete membership application workflow."""

    def test_complete_application_workflow(self):
        """Test the complete workflow from application to approval."""
        # Create a member manager who can review applications
        manager = Member.objects.create_user(
            username="manager",
            email="manager@example.com",
            password="testpass",
            member_manager=True,
            membership_status="Full Member",
        )

        # Submit application
        app_data = {
            "first_name": "Alice",
            "last_name": "Smith",
            "email": "alice@example.com",
            "phone": "555-123-4567",
            "address_line1": "456 Oak Ave",
            "city": "Springfield",
            "state": "IL",
            "zip_code": "62701",
            "emergency_contact_name": "Bob Smith",
            "emergency_contact_relationship": "Husband",
            "emergency_contact_phone": "555-987-6543",
            "soaring_goals": "I want to become a skilled glider pilot",
            "pilot_certificate_number": "1234567",
            "glider_rating": "student",
            "total_flight_hours": 25,
            "glider_flight_hours": 5,
            "agrees_to_terms": True,
            "agrees_to_safety_rules": True,
            "agrees_to_financial_obligations": True,
        }

        client = Client()
        response = client.post(reverse("members:membership_application"), app_data)
        assert response.status_code == 302  # Success redirect

        # Verify application was created
        app = MembershipApplication.objects.get(email="alice@example.com")
        assert app.status == "pending"
        assert app.can_be_approved() is True

        # Manager reviews and approves application
        member = app.approve_application(reviewed_by=manager)

        # Verify member account was created correctly
        assert member.username == "alice@example.com"
        assert member.email == "alice@example.com"
        assert member.first_name == "Alice"
        assert member.last_name == "Smith"
        assert member.pilot_certificate_number == "1234567"
        assert member.glider_rating == "student"

        # Verify application status updated
        app.refresh_from_db()
        assert app.status == "approved"
        assert app.member_account == member
        assert app.reviewed_by == manager
        assert app.reviewed_at is not None
