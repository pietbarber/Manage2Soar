"""
Tests for manual towplane addition functionality.
Tests the ability to add towplanes for rental-only usage (Biff's scenario).
"""

from django.test import TestCase
from django.urls import reverse

from logsheet.models import Airfield, Logsheet, Towplane, TowplaneCloseout
from members.models import Member
from siteconfig.models import SiteConfiguration


class ManualTowplaneAdditionTestCase(TestCase):
    """Test manual towplane addition for rental-only scenarios."""

    def setUp(self):
        """Set up test data for Biff's scenario."""
        # Enable towplane rentals in site configuration
        self.config = SiteConfiguration.objects.create(
            club_name="Test Soaring Club",
            domain_name="test.com",
            club_abbreviation="TSC",
            allow_towplane_rental=True,  # Enable rental functionality
        )

        # Create Biff as a member
        self.biff = Member.objects.create(
            username="biff",
            password="testpass",
            first_name="Biff",
            last_name="Tannen",
            membership_status="Full Member",
            email="biff@example.com",
        )

        # Create Husky towplane with rental rate
        self.husky = Towplane.objects.create(
            name="Husky",
            n_number="N6085S",
            is_active=True,
            club_owned=True,
            hourly_rental_rate=95.00,
        )

        # Create Pawnee as additional towplane option
        self.pawnee = Towplane.objects.create(
            name="Pawnee",
            n_number="N123PA",
            is_active=True,
            club_owned=True,
            hourly_rental_rate=85.00,
        )

        # Create airfield and logsheet for Tuesday (no operations day)
        self.airfield = Airfield.objects.create(
            name="Test Airfield", identifier="TEST", is_active=True
        )

        self.tuesday_logsheet = Logsheet.objects.create(
            log_date="2023-06-13",  # A Tuesday
            airfield=self.airfield,
            created_by=self.biff,
        )

    def test_logsheet_initially_has_no_towplane_closeouts(self):
        """Test that new logsheet has no towplane closeouts initially."""
        closeouts = TowplaneCloseout.objects.filter(logsheet=self.tuesday_logsheet)
        self.assertEqual(closeouts.count(), 0)

    def test_available_towplanes_shown_when_rentals_enabled(self):
        """Test that available towplanes appear in the add form when rentals enabled."""
        self.client.force_login(self.biff)
        url = reverse(
            "logsheet:edit_logsheet_closeout", kwargs={"pk": self.tuesday_logsheet.pk}
        )
        response = self.client.get(url)

        # Should show the manual addition form
        self.assertContains(response, "Add Towplane for Rental Usage")
        self.assertContains(response, "Husky (N6085S)")
        self.assertContains(response, "Pawnee (N123PA)")
        self.assertContains(response, "$95.00/hour")  # Husky rate
        self.assertContains(response, "$85.00/hour")  # Pawnee rate

    def test_available_towplanes_hidden_when_rentals_disabled(self):
        """Test that manual addition form is hidden when rentals disabled."""
        # Disable towplane rentals
        self.config.allow_towplane_rental = False
        self.config.save()

        self.client.force_login(self.biff)
        url = reverse(
            "logsheet:edit_logsheet_closeout", kwargs={"pk": self.tuesday_logsheet.pk}
        )
        response = self.client.get(url)

        # Should not show the manual addition form
        self.assertNotContains(response, "Add Towplane for Rental Usage")

    def test_manually_add_husky_for_rental(self):
        """Test Biff's scenario: manually add Husky for personal flight."""
        self.client.force_login(self.biff)

        # Add Husky towplane manually
        add_url = reverse(
            "logsheet:add_towplane_closeout", kwargs={"pk": self.tuesday_logsheet.pk}
        )
        response = self.client.post(add_url, {"towplane": self.husky.pk})

        # Should redirect back to closeout edit page
        self.assertEqual(response.status_code, 302)

        # Verify closeout was created
        closeout = TowplaneCloseout.objects.get(
            logsheet=self.tuesday_logsheet, towplane=self.husky
        )
        self.assertIsNotNone(closeout)

        # Check that closeout form now shows Husky
        edit_url = reverse(
            "logsheet:edit_logsheet_closeout", kwargs={"pk": self.tuesday_logsheet.pk}
        )
        response = self.client.get(edit_url)
        self.assertContains(response, "Husky")
        self.assertContains(response, "N6085S")

    def test_husky_no_longer_available_after_adding(self):
        """Test that Husky disappears from available list after being added."""
        self.client.force_login(self.biff)

        # Add Husky
        add_url = reverse(
            "logsheet:add_towplane_closeout", kwargs={"pk": self.tuesday_logsheet.pk}
        )
        self.client.post(add_url, {"towplane": self.husky.pk})

        # Check available towplanes
        edit_url = reverse(
            "logsheet:edit_logsheet_closeout", kwargs={"pk": self.tuesday_logsheet.pk}
        )
        response = self.client.get(edit_url)

        # Husky should no longer be in available towplanes
        context_towplanes = response.context["available_towplanes"]
        self.assertNotIn(self.husky, context_towplanes)

        # But Pawnee should still be available
        self.assertIn(self.pawnee, context_towplanes)

    def test_complete_biff_roanoke_scenario(self):
        """Test complete Biff's Roanoke flight scenario."""
        self.client.force_login(self.biff)

        # Step 1: Add Husky towplane manually
        add_url = reverse(
            "logsheet:add_towplane_closeout", kwargs={"pk": self.tuesday_logsheet.pk}
        )
        self.client.post(add_url, {"towplane": self.husky.pk})

        # Get the created closeout ID
        closeout = TowplaneCloseout.objects.get(
            logsheet=self.tuesday_logsheet, towplane=self.husky
        )

        # Step 2: Fill out closeout form with rental data (no duty officer required)
        edit_url = reverse(
            "logsheet:edit_logsheet_closeout", kwargs={"pk": self.tuesday_logsheet.pk}
        )

        form_data = {
            # Logsheet summary (minimal for rental-only day)
            "safety_issues": "All good",
            "equipment_issues": "None",
            "operations_summary": "No glider operations - Biff's personal flight to Roanoke",
            # NO duty_officer required for rental-only!
            # Towplane formset data
            "form-TOTAL_FORMS": "1",
            "form-INITIAL_FORMS": "1",
            "form-MIN_NUM_FORMS": "0",
            "form-MAX_NUM_FORMS": "1000",
            "form-0-id": closeout.id,  # Actual closeout ID
            "form-0-towplane": self.husky.pk,
            "form-0-start_tach": "1250.0",
            "form-0-end_tach": "1252.3",  # 2.3 hours flight
            "form-0-fuel_added": "18.0",
            "form-0-rental_hours_chargeable": "2.3",  # All flight time is rental
            "form-0-rental_charged_to": self.biff.pk,
            "form-0-notes": "Personal flight to Roanoke - no club operations",
        }

        response = self.client.post(edit_url, form_data)

        # Should redirect on successful save (no validation errors)
        self.assertEqual(response.status_code, 302)

        # Verify data was saved correctly
        closeout = TowplaneCloseout.objects.get(
            logsheet=self.tuesday_logsheet, towplane=self.husky
        )

        from decimal import Decimal

        self.assertEqual(closeout.start_tach, Decimal("1250.0"))
        self.assertEqual(closeout.end_tach, Decimal("1252.3"))
        self.assertEqual(closeout.fuel_added, Decimal("18.0"))
        self.assertEqual(closeout.rental_hours_chargeable, Decimal("2.3"))
        self.assertEqual(closeout.rental_charged_to, self.biff)
        self.assertEqual(closeout.rental_cost, Decimal("218.50"))  # 2.3 * $95.00
        self.assertIn("Personal flight to Roanoke", closeout.notes)

    def test_mixed_operations_scenario(self):
        """Test scenario 2: Pawnee does tows, Husky added manually for rental."""
        # This would require creating some flights with Pawnee first
        # For now, just test that we can add Husky when other towplanes exist

        # Create a closeout for Pawnee (simulating it having flights)
        TowplaneCloseout.objects.create(
            logsheet=self.tuesday_logsheet,
            towplane=self.pawnee,
            start_tach=800.0,
            end_tach=810.0,  # Had some operations
        )

        self.client.force_login(self.biff)

        # Should still be able to add Husky manually
        add_url = reverse(
            "logsheet:add_towplane_closeout", kwargs={"pk": self.tuesday_logsheet.pk}
        )
        response = self.client.post(add_url, {"towplane": self.husky.pk})

        self.assertEqual(response.status_code, 302)

        # Should now have closeouts for both towplanes
        closeouts = TowplaneCloseout.objects.filter(logsheet=self.tuesday_logsheet)
        self.assertEqual(closeouts.count(), 2)

        towplanes = [c.towplane for c in closeouts]
        self.assertIn(self.pawnee, towplanes)
        self.assertIn(self.husky, towplanes)

    def test_add_towplane_requires_authentication(self):
        """Test that adding towplanes requires user to be logged in."""
        # Don't log in
        add_url = reverse(
            "logsheet:add_towplane_closeout", kwargs={"pk": self.tuesday_logsheet.pk}
        )
        response = self.client.post(add_url, {"towplane": self.husky.pk})

        # Should redirect to login (302) or return forbidden
        self.assertIn(response.status_code, [302, 403])

    def test_add_invalid_towplane_shows_error(self):
        """Test error handling for invalid towplane selection."""
        self.client.force_login(self.biff)

        add_url = reverse(
            "logsheet:add_towplane_closeout", kwargs={"pk": self.tuesday_logsheet.pk}
        )

        # Try to add without selecting towplane
        response = self.client.post(add_url, {"towplane": ""})
        self.assertEqual(response.status_code, 302)  # Redirects back

        # Try to add non-existent towplane
        response = self.client.post(add_url, {"towplane": 99999})
        self.assertEqual(response.status_code, 404)  # Towplane not found

    def test_add_same_towplane_twice_shows_message(self):
        """Test that adding the same towplane twice shows appropriate message."""
        self.client.force_login(self.biff)

        add_url = reverse(
            "logsheet:add_towplane_closeout", kwargs={"pk": self.tuesday_logsheet.pk}
        )

        # Add Husky first time
        response = self.client.post(add_url, {"towplane": self.husky.pk}, follow=True)
        messages = [str(m) for m in response.context["messages"]]
        self.assertTrue(any("Added Husky" in msg for msg in messages))

        # Add Husky second time
        response = self.client.post(add_url, {"towplane": self.husky.pk}, follow=True)
        messages = [str(m) for m in response.context["messages"]]
        self.assertTrue(any("already in the closeout form" in msg for msg in messages))
