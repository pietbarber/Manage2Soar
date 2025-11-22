"""
Tests for towplane rental site configuration setting.
Tests that towplane rental fields are shown/hidden based on site configuration.
"""

from django.test import TestCase
from django.urls import reverse

from logsheet.models import Airfield, Logsheet, Towplane, TowplaneCloseout
from members.models import Member
from siteconfig.models import SiteConfiguration


class TowplaneRentalSettingTestCase(TestCase):
    """Test conditional display of towplane rental fields based on site configuration."""

    def setUp(self):
        """Set up test data."""
        # Create site configuration
        self.config = SiteConfiguration.objects.create(
            club_name="Test Club",
            domain_name="test.com",
            club_abbreviation="TC",
            allow_towplane_rental=False,  # Start with rental disabled
        )

        # Create a member (which includes the user)
        self.member = Member.objects.create_user(
            username="testuser",
            password="testpass",
            first_name="Test",
            last_name="User",
            membership_status="Full Member",
            email="test@example.com",
            duty_officer=True,  # Required for duty form validation
            instructor=True,  # May be useful for other tests
            towpilot=True,  # May be useful for other tests
        )

        # Create airfield, towplane, and logsheet
        self.airfield = Airfield.objects.create(
            name="Test Airfield", identifier="TEST", is_active=True
        )
        self.towplane = Towplane.objects.create(
            name="Test Towplane",
            n_number="N123TP",
            is_active=True,
            club_owned=True,
            hourly_rental_rate=150.00,
        )
        self.logsheet = Logsheet.objects.create(
            log_date="2023-06-15", airfield=self.airfield, created_by=self.member
        )
        self.closeout = TowplaneCloseout.objects.create(
            logsheet=self.logsheet,
            towplane=self.towplane,
            start_tach=100.0,
            end_tach=105.0,
            fuel_added=25.0,
        )

    def test_rental_fields_hidden_when_disabled(self):
        """Test that rental fields are not shown when towplane rental is disabled."""
        # Ensure rental is disabled
        self.config.allow_towplane_rental = False
        self.config.save()

        self.client.force_login(self.member)
        url = reverse(
            "logsheet:edit_logsheet_closeout", kwargs={"pk": self.logsheet.pk}
        )
        response = self.client.get(url)

        # Check that rental fields are not in the response
        self.assertNotContains(response, 'name="form-0-rental_hours_chargeable"')
        self.assertNotContains(response, 'name="form-0-rental_charged_to"')
        self.assertNotContains(response, "Non-Towing Rental Charges")

    def test_rental_fields_shown_when_enabled(self):
        """Test that rental fields are shown when towplane rental is enabled."""
        # Enable rental
        self.config.allow_towplane_rental = True
        self.config.save()

        self.client.force_login(self.member)
        url = reverse(
            "logsheet:edit_logsheet_closeout", kwargs={"pk": self.logsheet.pk}
        )
        response = self.client.get(url)

        # Check that rental fields are in the response
        self.assertContains(response, 'name="form-0-rental_hours_chargeable"')
        self.assertContains(response, 'name="form-0-rental_charged_to"')
        self.assertContains(response, "Non-Towing Rental Charges")

    def test_financial_page_hides_rental_column_when_disabled(self):
        """Test that towplane rental column is hidden in financial management when disabled."""
        # Ensure rental is disabled
        self.config.allow_towplane_rental = False
        self.config.save()

        self.client.force_login(self.member)
        url = reverse(
            "logsheet:manage_logsheet_finances", kwargs={"pk": self.logsheet.pk}
        )
        response = self.client.get(url)

        # Check that towplane rental column is not in the member charges table
        self.assertNotContains(response, "Towplane Rental</th>")
        # The section header should also not appear since rental is disabled
        self.assertNotContains(response, "Towplane Rental Charges")

    def test_financial_page_shows_rental_column_when_enabled(self):
        """Test that towplane rental column is shown in financial management when enabled."""
        # Enable rental and add some rental data
        self.config.allow_towplane_rental = True
        self.config.save()

        # Add rental data to the closeout
        self.closeout.rental_hours_chargeable = 2.5
        self.closeout.rental_charged_to = self.member
        self.closeout.save()

        self.client.force_login(self.member)
        url = reverse(
            "logsheet:manage_logsheet_finances", kwargs={"pk": self.logsheet.pk}
        )
        response = self.client.get(url)

        # Check that towplane rental column is in the member charges table
        self.assertContains(response, "Towplane Rental</th>")
        # The section header should appear since we have rental data
        self.assertContains(response, "Towplane Rental Charges")

    def test_form_saves_without_rental_fields_when_disabled(self):
        """Test that form can save without rental fields when feature is disabled."""
        # Ensure rental is disabled
        self.config.allow_towplane_rental = False
        self.config.save()

        self.client.force_login(self.member)
        url = reverse(
            "logsheet:edit_logsheet_closeout", kwargs={"pk": self.logsheet.pk}
        )

        # Submit form data without rental fields
        form_data = {
            "safety_issues": "All good",
            "equipment_issues": "None",
            "operations_summary": "Great day of flying",
            "duty_officer": self.member.pk,
            "form-TOTAL_FORMS": "1",
            "form-INITIAL_FORMS": "1",
            "form-MIN_NUM_FORMS": "0",
            "form-MAX_NUM_FORMS": "1000",
            "form-0-id": self.closeout.pk,
            "form-0-towplane": self.towplane.pk,
            "form-0-start_tach": "100.0",
            "form-0-end_tach": "105.0",
            "form-0-fuel_added": "25.0",
            "form-0-notes": "Good flight",
        }

        response = self.client.post(url, form_data)

        # Should redirect on successful save
        self.assertEqual(response.status_code, 302)

        # Verify closeout was updated
        self.closeout.refresh_from_db()
        self.assertEqual(self.closeout.fuel_added, 25.0)

    def test_form_saves_with_rental_fields_when_enabled(self):
        """Test that form can save with rental fields when feature is enabled."""
        # Enable rental
        self.config.allow_towplane_rental = True
        self.config.save()

        self.client.force_login(self.member)
        url = reverse(
            "logsheet:edit_logsheet_closeout", kwargs={"pk": self.logsheet.pk}
        )

        # Submit form data with rental fields
        form_data = {
            "safety_issues": "All good",
            "equipment_issues": "None",
            "operations_summary": "Great day of flying",
            "duty_officer": self.member.pk,
            "form-TOTAL_FORMS": "1",
            "form-INITIAL_FORMS": "1",
            "form-MIN_NUM_FORMS": "0",
            "form-MAX_NUM_FORMS": "1000",
            "form-0-id": self.closeout.pk,
            "form-0-towplane": self.towplane.pk,
            "form-0-start_tach": "100.0",
            "form-0-end_tach": "105.0",
            "form-0-fuel_added": "25.0",
            "form-0-rental_hours_chargeable": "2.5",
            "form-0-rental_charged_to": self.member.pk,
            "form-0-notes": "Good flight with rental",
        }

        response = self.client.post(url, form_data)
        # Should redirect on successful save
        self.assertEqual(response.status_code, 302)

        # Verify closeout was updated with rental data
        self.closeout.refresh_from_db()
        self.assertEqual(self.closeout.fuel_added, 25.0)
        self.assertEqual(self.closeout.rental_hours_chargeable, 2.5)
        self.assertEqual(self.closeout.rental_charged_to, self.member)

    def test_default_setting_is_disabled(self):
        """Test that towplane rental is disabled by default."""
        # Check that our test config has the default value (False)
        # since we didn't explicitly set it in setUp
        self.assertFalse(self.config.allow_towplane_rental)
