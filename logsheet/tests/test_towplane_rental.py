"""
Test towplane rental functionality for Issue 123.
Tests non-towing towplane charges (sightseeing, flight reviews, retrieval).
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from logsheet.models import Airfield, Logsheet, Towplane, TowplaneCloseout
from members.models import Member
from siteconfig.models import SiteConfiguration

User = get_user_model()


class TowplaneRentalTestCase(TestCase):
    """Test towplane rental cost calculations and form integration."""

    def setUp(self):
        """Set up test data."""
        # Create test user
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com"
        )

        # Create test member
        self.member = Member.objects.create(
            user=self.user,
            first_name="Test",
            last_name="User",
            membership_status="Full Member",
        )

        # Create test towplane with rental rate
        self.towplane = Towplane.objects.create(
            name="Test Husky", n_number="N123TEST", hourly_rental_rate=Decimal("95.00")
        )

        # Create test airfield
        self.airfield = Airfield.objects.create(identifier="TEST", name="Test Airfield")

        # Create test logsheet
        self.logsheet = Logsheet.objects.create(
            log_date="2025-11-21", airfield=self.airfield, created_by=self.member
        )

    def test_towplane_rental_rate_field(self):
        """Test that towplane rental rate field works correctly."""
        # Test towplane with rental rate
        self.assertEqual(self.towplane.hourly_rental_rate, Decimal("95.00"))

        # Test towplane without rental rate
        towplane_no_rate = Towplane.objects.create(
            name="No Rate Towplane", n_number="N999NONE"
        )
        self.assertIsNone(towplane_no_rate.hourly_rental_rate)

    def test_towplane_closeout_rental_cost_calculation(self):
        """Test rental cost calculation in TowplaneCloseout."""
        closeout = TowplaneCloseout.objects.create(
            logsheet=self.logsheet,
            towplane=self.towplane,
            start_tach=Decimal("100.0"),
            end_tach=Decimal("103.5"),
            tach_time=Decimal("3.5"),
            fuel_added=Decimal("12.5"),
            rental_hours_chargeable=Decimal("2.0"),  # 2 hours of rental
        )

        # Test rental cost calculation: 2.0 hours * $95.00/hour = $190.00
        expected_cost = Decimal("190.00")
        self.assertEqual(closeout.rental_cost, expected_cost)
        self.assertEqual(closeout.rental_cost_display, "$190.00")

    def test_towplane_closeout_no_rental_hours(self):
        """Test closeout with no rental hours charged."""
        closeout = TowplaneCloseout.objects.create(
            logsheet=self.logsheet,
            towplane=self.towplane,
            start_tach=Decimal("100.0"),
            end_tach=Decimal("103.5"),
            tach_time=Decimal("3.5"),
            fuel_added=Decimal("12.5"),
            # No rental_hours_chargeable set
        )

        # Should return None when no rental hours
        self.assertIsNone(closeout.rental_cost)
        self.assertEqual(closeout.rental_cost_display, "—")

    def test_towplane_closeout_no_rental_rate(self):
        """Test closeout with towplane that has no rental rate."""
        towplane_no_rate = Towplane.objects.create(
            name="No Rate Towplane", n_number="N999NONE"
        )

        closeout = TowplaneCloseout.objects.create(
            logsheet=self.logsheet,
            towplane=towplane_no_rate,
            rental_hours_chargeable=Decimal("2.0"),
        )

        # Should return None when no rental rate set
        self.assertIsNone(closeout.rental_cost)
        self.assertEqual(closeout.rental_cost_display, "—")

    def test_partial_rental_hours(self):
        """Test rental calculation with partial hours."""
        closeout = TowplaneCloseout.objects.create(
            logsheet=self.logsheet,
            towplane=self.towplane,
            rental_hours_chargeable=Decimal("1.5"),  # 1.5 hours
        )

        # Test calculation: 1.5 hours * $95.00/hour = $142.50
        expected_cost = Decimal("142.50")
        self.assertEqual(closeout.rental_cost, expected_cost)
        self.assertEqual(closeout.rental_cost_display, "$142.50")

    def test_zero_rental_hours(self):
        """Test with zero rental hours."""
        closeout = TowplaneCloseout.objects.create(
            logsheet=self.logsheet,
            towplane=self.towplane,
            rental_hours_chargeable=Decimal("0.0"),
        )

        # Should return None for zero hours
        self.assertIsNone(closeout.rental_cost)

    def test_multiple_towplane_closeouts_different_rates(self):
        """Test multiple towplanes with different rental rates."""
        # Create second towplane with different rate
        towplane2 = Towplane.objects.create(
            name="Test Pawnee", n_number="N456TEST", hourly_rental_rate=Decimal("85.00")
        )

        # Create closeouts for both towplanes
        closeout1 = TowplaneCloseout.objects.create(
            logsheet=self.logsheet,
            towplane=self.towplane,
            rental_hours_chargeable=Decimal("2.0"),  # Husky: 2.0 * $95 = $190
        )

        closeout2 = TowplaneCloseout.objects.create(
            logsheet=self.logsheet,
            towplane=towplane2,
            rental_hours_chargeable=Decimal("1.0"),  # Pawnee: 1.0 * $85 = $85
        )

        self.assertEqual(closeout1.rental_cost, Decimal("190.00"))
        self.assertEqual(closeout2.rental_cost, Decimal("85.00"))

    def test_high_precision_calculations(self):
        """Test rental calculations with high precision decimals."""
        closeout = TowplaneCloseout.objects.create(
            logsheet=self.logsheet,
            towplane=self.towplane,
            rental_hours_chargeable=Decimal("0.1"),  # 6 minutes
        )

        # 0.1 hours * $95.00/hour = $9.50
        expected_cost = Decimal("9.50")
        self.assertEqual(closeout.rental_cost, expected_cost)


class TowplaneRentalFormTestCase(TestCase):
    """Test forms integration for towplane rental."""

    def setUp(self):
        """Set up test data."""
        # Enable towplane rentals in site configuration
        self.config = SiteConfiguration.objects.create(
            club_name="Test Club",
            domain_name="test.com",
            club_abbreviation="TC",
            allow_towplane_rental=True,  # Enable rental functionality
        )

        self.user = User.objects.create_user(
            username="testuser", email="test@example.com"
        )

        self.member = Member.objects.create(
            user=self.user,
            first_name="Test",
            last_name="User",
            membership_status="Full Member",
        )

        self.towplane = Towplane.objects.create(
            name="Test Husky", n_number="N123TEST", hourly_rental_rate=Decimal("95.00")
        )

        self.airfield = Airfield.objects.create(identifier="TEST", name="Test Airfield")

        self.logsheet = Logsheet.objects.create(
            log_date="2025-11-21", airfield=self.airfield, created_by=self.member
        )

    def test_towplane_closeout_form_includes_rental_field(self):
        """Test that TowplaneCloseoutForm includes rental_hours_chargeable."""
        from logsheet.forms import TowplaneCloseoutForm

        form = TowplaneCloseoutForm()
        self.assertIn("rental_hours_chargeable", form.fields)

        # Check field label and help text
        field = form.fields["rental_hours_chargeable"]
        self.assertEqual(field.label, "Rental Hours (Non-Towing)")
        self.assertIn("non-towing usage", field.help_text)

    def test_form_saves_rental_hours(self):
        """Test that form correctly saves rental hours data."""
        from logsheet.forms import TowplaneCloseoutForm

        form_data = {
            "towplane": self.towplane.pk,
            "start_tach": "100.0",
            "end_tach": "103.5",
            "fuel_added": "12.5",
            "rental_hours_chargeable": "2.0",
            "rental_charged_to": self.member.pk,  # Required field when rentals enabled
            "notes": "Test flight review",
        }

        form = TowplaneCloseoutForm(data=form_data)
        self.assertTrue(form.is_valid())

        # Create closeout instance
        closeout = form.save(commit=False)
        closeout.logsheet = self.logsheet
        closeout.save()

        # Verify data was saved correctly
        self.assertEqual(closeout.rental_hours_chargeable, Decimal("2.0"))
        self.assertEqual(closeout.rental_cost, Decimal("190.00"))


class TowplaneRentalUseCaseTestCase(TestCase):
    """Test real-world use cases mentioned in Issue 123."""

    def setUp(self):
        """Set up test data for use cases."""
        self.user = User.objects.create_user(
            username="testpilot", email="pilot@example.com"
        )

        self.member = Member.objects.create(
            user=self.user,
            first_name="Test",
            last_name="Pilot",
            membership_status="Full Member",
        )

        # Create Husky towplane (mentioned in issue)
        self.husky = Towplane.objects.create(
            name="Husky", n_number="N6085S", hourly_rental_rate=Decimal("95.00")
        )

        self.airfield = Airfield.objects.create(
            identifier="KFRR", name="Front Royal Warren County Airport"
        )

        self.logsheet = Logsheet.objects.create(
            log_date="2025-11-21", airfield=self.airfield, created_by=self.member
        )

    def test_flight_review_scenario(self):
        """Test scenario: Flight review in the Husky (from issue description)."""
        # Create closeout for flight review
        closeout = TowplaneCloseout.objects.create(
            logsheet=self.logsheet,
            towplane=self.husky,
            start_tach=Decimal("1250.0"),
            end_tach=Decimal("1252.5"),  # 2.5 hours flight time
            tach_time=Decimal("2.5"),
            fuel_added=Decimal("18.0"),
            rental_hours_chargeable=Decimal("2.5"),  # All time is rental
            notes="Flight review with rare towplane instructor",
        )

        # Should calculate: 2.5 hours * $95/hour = $237.50
        expected_cost = Decimal("237.50")
        self.assertEqual(closeout.rental_cost, expected_cost)
        self.assertEqual(closeout.rental_cost_display, "$237.50")

    def test_bergfalke_retrieval_scenario(self):
        """Test scenario: Towplane retrieval flight (from issue description)."""
        # Create closeout for retrieval flight
        closeout = TowplaneCloseout.objects.create(
            logsheet=self.logsheet,
            towplane=self.husky,
            start_tach=Decimal("1300.0"),
            end_tach=Decimal("1301.5"),  # 1.5 hours for retrieval
            tach_time=Decimal("1.5"),
            fuel_added=Decimal("8.0"),
            rental_hours_chargeable=Decimal("1.5"),  # Retrieval time
            notes="Bergfalke retrieval from Flying Cow to Woodstock",
        )

        # Should calculate: 1.5 hours * $95/hour = $142.50
        expected_cost = Decimal("142.50")
        self.assertEqual(closeout.rental_cost, expected_cost)

    def test_sightseeing_flight_scenario(self):
        """Test scenario: Sightseeing flight (from issue comments)."""
        # Create closeout for sightseeing flight
        closeout = TowplaneCloseout.objects.create(
            logsheet=self.logsheet,
            towplane=self.husky,
            start_tach=Decimal("1400.0"),
            end_tach=Decimal("1401.2"),  # 1.2 hours sightseeing
            tach_time=Decimal("1.2"),
            fuel_added=Decimal("6.5"),
            rental_hours_chargeable=Decimal("1.2"),  # All time is rental
            notes="Tuesday sightseeing flight - no glider operations",
        )

        # Should calculate: 1.2 hours * $95/hour = $114.00
        expected_cost = Decimal("114.00")
        self.assertEqual(closeout.rental_cost, expected_cost)

    def test_mixed_towing_and_rental(self):
        """Test scenario: Mix of towing and rental on same day."""
        # Create closeout where some hours are towing, some are rental
        closeout = TowplaneCloseout.objects.create(
            logsheet=self.logsheet,
            towplane=self.husky,
            start_tach=Decimal("1500.0"),
            end_tach=Decimal("1504.0"),  # 4.0 total hours
            tach_time=Decimal("4.0"),
            fuel_added=Decimal("25.0"),
            rental_hours_chargeable=Decimal("1.0"),  # Only 1 hour of rental
            notes="Regular towing ops plus 1 hour flight review",
        )

        # Only the 1 hour of rental should be charged
        # 1.0 hours * $95/hour = $95.00
        expected_cost = Decimal("95.00")
        self.assertEqual(closeout.rental_cost, expected_cost)
