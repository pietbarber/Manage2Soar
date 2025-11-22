"""
Tests for towplane-specific charging system (Issue #67).

Tests different towplane charges, flexible pricing schemes,
and backward compatibility with existing TowRate system.
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from logsheet.models import (
    Airfield,
    Flight,
    Logsheet,
    Towplane,
    TowplaneChargeScheme,
    TowplaneChargeTier,
    TowRate,
)
from members.models import Member

User = get_user_model()


class TowplaneChargeSchemeTestCase(TestCase):
    """Test basic TowplaneChargeScheme functionality."""

    def setUp(self):
        self.towplane = Towplane.objects.create(
            name="Test Pawnee", n_number="N123TP", make="Piper", model="PA-25 Pawnee"
        )

    def test_create_charge_scheme(self):
        """Test creating a basic charge scheme."""
        scheme = TowplaneChargeScheme.objects.create(
            towplane=self.towplane,
            name="Standard Pawnee Rates",
            hookup_fee=Decimal("7.50"),
            description="Standard rates for our Pawnee",
        )

        self.assertEqual(str(scheme), "Test Pawnee - Standard Pawnee Rates")
        self.assertEqual(scheme.hookup_fee, Decimal("7.50"))
        self.assertTrue(scheme.is_active)

    def test_calculate_cost_with_no_tiers(self):
        """Test cost calculation with only hookup fee (no tiers)."""
        scheme = TowplaneChargeScheme.objects.create(
            towplane=self.towplane, name="Hookup Only", hookup_fee=Decimal("5.00")
        )

        # Should return just the hookup fee for any altitude
        cost = scheme.calculate_tow_cost(2000)
        self.assertEqual(cost, Decimal("5.00"))

        cost = scheme.calculate_tow_cost(3000)
        self.assertEqual(cost, Decimal("5.00"))

    def test_calculate_cost_inactive_scheme(self):
        """Test that inactive schemes return None."""
        scheme = TowplaneChargeScheme.objects.create(
            towplane=self.towplane, name="Inactive Scheme", is_active=False
        )

        cost = scheme.calculate_tow_cost(2000)
        self.assertIsNone(cost)


class TowplaneChargeTierTestCase(TestCase):
    """Test TowplaneChargeTier functionality."""

    def setUp(self):
        self.towplane = Towplane.objects.create(
            name="Test Husky", n_number="N456TH", make="Aviat", model="A-1C Husky"
        )

        self.scheme = TowplaneChargeScheme.objects.create(
            towplane=self.towplane,
            name="Husky Complex Rates",
            hookup_fee=Decimal("7.50"),
        )

    def test_create_flat_rate_tier(self):
        """Test creating a flat rate tier."""
        tier = TowplaneChargeTier.objects.create(
            charge_scheme=self.scheme,
            altitude_start=0,
            altitude_end=1000,
            rate_type="flat",
            rate_amount=Decimal("10.00"),
            description="Base tow to pattern altitude",
        )

        # Should charge flat rate regardless of altitude within tier
        cost = tier.calculate_cost(500)
        self.assertEqual(cost, Decimal("10.00"))

        cost = tier.calculate_cost(999)
        self.assertEqual(cost, Decimal("10.00"))

    def test_create_per_1000ft_tier(self):
        """Test creating a per-1000ft tier."""
        tier = TowplaneChargeTier.objects.create(
            charge_scheme=self.scheme,
            altitude_start=1000,
            altitude_end=3000,
            rate_type="per_1000ft",
            rate_amount=Decimal("5.00"),
        )

        # Should charge per 1000ft increment (rounded up)
        cost = tier.calculate_cost(500)  # 1 increment
        self.assertEqual(cost, Decimal("5.00"))

        cost = tier.calculate_cost(1500)  # 2 increments
        self.assertEqual(cost, Decimal("10.00"))

        cost = tier.calculate_cost(2000)  # 2 increments
        self.assertEqual(cost, Decimal("10.00"))

        cost = tier.calculate_cost(2001)  # 3 increments
        self.assertEqual(cost, Decimal("15.00"))

    def test_create_per_100ft_tier(self):
        """Test creating a per-100ft tier."""
        tier = TowplaneChargeTier.objects.create(
            charge_scheme=self.scheme,
            altitude_start=3000,
            rate_type="per_100ft",  # No altitude_end = unlimited
            rate_amount=Decimal("0.50"),
        )

        # Should charge per 100ft increment (rounded up)
        cost = tier.calculate_cost(150)  # 2 increments
        self.assertEqual(cost, Decimal("1.00"))

        cost = tier.calculate_cost(500)  # 5 increments
        self.assertEqual(cost, Decimal("2.50"))

    def test_tier_validation(self):
        """Test tier altitude range validation."""
        # End altitude must be greater than start
        with self.assertRaises(ValidationError):
            tier = TowplaneChargeTier(
                charge_scheme=self.scheme,
                altitude_start=2000,
                altitude_end=1000,  # Invalid: end < start
                rate_type="flat",
                rate_amount=Decimal("10.00"),
            )
            tier.full_clean()

    def test_inactive_tier(self):
        """Test that inactive tiers return zero cost."""
        tier = TowplaneChargeTier.objects.create(
            charge_scheme=self.scheme,
            altitude_start=0,
            altitude_end=1000,
            rate_type="flat",
            rate_amount=Decimal("10.00"),
            is_active=False,
        )

        cost = tier.calculate_cost(500)
        self.assertEqual(cost, Decimal("0.00"))


class ComplexTowplanePricingTestCase(TestCase):
    """Test complex tiered pricing scenarios."""

    def setUp(self):
        self.towplane = Towplane.objects.create(
            name="Premium Tow Plane", n_number="N789PT", make="Cessna", model="180"
        )

        # Create scheme matching issue example:
        # $7.50 hookup fee
        # $10 for first 1000 feet
        # $5 for each additional 1000 feet
        self.scheme = TowplaneChargeScheme.objects.create(
            towplane=self.towplane, name="Premium Rates", hookup_fee=Decimal("7.50")
        )

        # First 1000ft: $10 flat
        TowplaneChargeTier.objects.create(
            charge_scheme=self.scheme,
            altitude_start=0,
            altitude_end=1000,
            rate_type="flat",
            rate_amount=Decimal("10.00"),
            description="Base tow to 1000ft",
        )

        # Above 1000ft: $5 per 1000ft
        TowplaneChargeTier.objects.create(
            charge_scheme=self.scheme,
            altitude_start=1000,
            rate_type="per_1000ft",
            rate_amount=Decimal("5.00"),
            description="Additional altitude",
        )

    def test_complex_pricing_calculation(self):
        """Test the complex pricing scenario from the issue."""
        # 500ft: hookup + first tier = $7.50 + $10.00 = $17.50
        cost = self.scheme.calculate_tow_cost(500)
        self.assertEqual(cost, Decimal("17.50"))

        # 1000ft: hookup + first tier = $7.50 + $10.00 = $17.50
        cost = self.scheme.calculate_tow_cost(1000)
        self.assertEqual(cost, Decimal("17.50"))

        # 1500ft: hookup + first tier + 1 additional = $7.50 + $10.00 + $5.00 = $22.50
        cost = self.scheme.calculate_tow_cost(1500)
        self.assertEqual(cost, Decimal("22.50"))

        # 2000ft: hookup + first tier + 1 additional = $7.50 + $10.00 + $5.00 = $22.50
        cost = self.scheme.calculate_tow_cost(2000)
        self.assertEqual(cost, Decimal("22.50"))

        # 2500ft: hookup + first tier + 2 additional = $7.50 + $10.00 + $10.00 = $27.50
        cost = self.scheme.calculate_tow_cost(2500)
        self.assertEqual(cost, Decimal("27.50"))

        # 3000ft: hookup + first tier + 2 additional = $7.50 + $10.00 + $10.00 = $27.50
        cost = self.scheme.calculate_tow_cost(3000)
        self.assertEqual(cost, Decimal("27.50"))


class FlightTowCostIntegrationTestCase(TestCase):
    """Test integration with Flight model tow cost calculation."""

    def setUp(self):
        # Create user and member
        self.user = User.objects.create_user(
            username="testpilot",
            email="pilot@example.com",
            first_name="Test",
            last_name="Pilot",
        )

        self.member = Member.objects.create(
            user=self.user, membership_status="Full Member"
        )

        # Create airfield and logsheet
        self.airfield = Airfield.objects.create(identifier="KTEST", name="Test Field")

        self.logsheet = Logsheet.objects.create(
            log_date="2025-01-01", airfield=self.airfield, created_by=self.member
        )

        # Create towplanes
        self.standard_towplane = Towplane.objects.create(
            name="Standard Tow", n_number="N123ST"
        )

        self.premium_towplane = Towplane.objects.create(
            name="Premium Tow", n_number="N456PT"
        )

        # Create global tow rates for fallback
        TowRate.objects.create(altitude=2000, price=Decimal("25.00"))
        TowRate.objects.create(altitude=3000, price=Decimal("30.00"))

        # Create premium towplane charge scheme
        premium_scheme = TowplaneChargeScheme.objects.create(
            towplane=self.premium_towplane,
            name="Premium Rates",
            hookup_fee=Decimal("10.00"),
        )

        TowplaneChargeTier.objects.create(
            charge_scheme=premium_scheme,
            altitude_start=0,
            rate_type="per_1000ft",
            rate_amount=Decimal("15.00"),
        )

    def test_flight_uses_towplane_specific_rates(self):
        """Test flight uses towplane-specific rates when available."""
        flight = Flight.objects.create(
            logsheet=self.logsheet,
            pilot=self.member,
            towplane=self.premium_towplane,
            release_altitude=2000,
        )

        # Should use premium scheme: $10 hookup + $30 (2 × $15) = $40
        cost = flight.tow_cost_calculated
        self.assertEqual(cost, Decimal("40.00"))

    def test_flight_falls_back_to_global_rates(self):
        """Test flight falls back to global TowRate when no scheme exists."""
        flight = Flight.objects.create(
            logsheet=self.logsheet,
            pilot=self.member,
            towplane=self.standard_towplane,
            release_altitude=2000,
        )

        # Should use global TowRate: $25.00
        cost = flight.tow_cost_calculated
        self.assertEqual(cost, Decimal("25.00"))

    def test_flight_with_inactive_scheme_falls_back(self):
        """Test flight falls back when towplane scheme is inactive."""
        # Create inactive scheme
        TowplaneChargeScheme.objects.create(
            towplane=self.standard_towplane,
            name="Inactive Scheme",
            is_active=False,
            hookup_fee=Decimal("100.00"),  # High fee to ensure it's not used
        )

        flight = Flight.objects.create(
            logsheet=self.logsheet,
            pilot=self.member,
            towplane=self.standard_towplane,
            release_altitude=2000,
        )

        # Should use global TowRate, not the inactive scheme
        cost = flight.tow_cost_calculated
        self.assertEqual(cost, Decimal("25.00"))

    def test_tow_cost_property_consistency(self):
        """Test that tow_cost property matches tow_cost_calculated."""
        flight = Flight.objects.create(
            logsheet=self.logsheet,
            pilot=self.member,
            towplane=self.premium_towplane,
            release_altitude=3000,
        )

        # Both properties should return the same value
        calculated_cost = flight.tow_cost_calculated
        property_cost = flight.tow_cost

        self.assertEqual(calculated_cost, property_cost)
        self.assertEqual(property_cost, Decimal("55.00"))  # $10 + (3 × $15)


class BackwardCompatibilityTestCase(TestCase):
    """Test backward compatibility with existing TowRate system."""

    def setUp(self):
        # Create towplane without charge scheme
        self.towplane = Towplane.objects.create(name="Old Towplane", n_number="N111OLD")

        # Create traditional tow rates (every 100ft like the real system)
        # This matches the pattern from tow_rate_import.py
        rates = [
            (0, "10.00"),
            (100, "10.00"),
            (200, "11.00"),
            (300, "12.00"),
            (400, "13.00"),
            (500, "15.00"),
            (600, "16.00"),
            (700, "17.00"),
            (800, "18.00"),
            (900, "19.00"),
            (1000, "15.00"),
            (1100, "16.00"),
            (1200, "17.00"),
            (1300, "18.00"),
            (1400, "19.00"),
            (1500, "15.00"),
            (1600, "16.00"),
            (1700, "17.00"),
            (1800, "18.00"),
            (1900, "19.00"),
            (2000, "20.00"),
            (2100, "21.00"),
            (2200, "22.00"),
            (2300, "23.00"),
            (2400, "24.00"),
            (2500, "20.00"),
            (2600, "21.00"),
            (2700, "22.00"),
            (2800, "23.00"),
            (2900, "24.00"),
            (3000, "25.00"),
            (3100, "26.00"),
            (3200, "27.00"),
            (3300, "28.00"),
            (3400, "29.00"),
            (3500, "25.00"),
            (3600, "26.00"),
            (3700, "27.00"),
            (3800, "28.00"),
            (3900, "29.00"),
            (4000, "30.00"),
            (4100, "31.00"),
            (4200, "32.00"),
            (4300, "33.00"),
            (4400, "34.00"),
            (4500, "30.00"),
        ]

        for altitude, price in rates:
            TowRate.objects.create(altitude=altitude, price=Decimal(price))

    def test_backward_compatibility_preserved(self):
        """Test that flights work exactly as before when no charge schemes exist."""
        # Create user and member for flight
        user = User.objects.create_user(username="oldpilot")
        member = Member.objects.create(user=user, membership_status="Full Member")

        # Create airfield and logsheet
        airfield = Airfield.objects.create(identifier="KTEST", name="Test Field")
        logsheet = Logsheet.objects.create(
            log_date="2025-01-01", airfield=airfield, created_by=member
        )

        # Test various altitudes
        test_cases = [
            (500, Decimal("15.00")),  # Uses 500ft rate (highest ≤ 500)
            (1500, Decimal("15.00")),  # Uses rate at 1500ft (highest ≤ 1500)
            (2500, Decimal("20.00")),  # Uses 2500ft rate (exact match)
            (3500, Decimal("25.00")),  # Uses 3500ft rate (exact match)
            (4500, Decimal("30.00")),  # Uses 4500ft rate (exact match)
        ]

        for altitude, expected_cost in test_cases:
            with self.subTest(altitude=altitude):
                flight = Flight.objects.create(
                    logsheet=logsheet,
                    pilot=member,
                    towplane=self.towplane,
                    release_altitude=altitude,
                )

                cost = flight.tow_cost_calculated
                self.assertEqual(
                    cost,
                    expected_cost,
                    f"Altitude {altitude}ft should cost ${expected_cost}, got ${cost}",
                )
