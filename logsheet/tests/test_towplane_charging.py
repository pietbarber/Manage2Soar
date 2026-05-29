"""
Tests for towplane-specific charging system (Issue #67).

Tests different towplane charges and flexible pricing schemes.
"""

from datetime import time
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from logsheet.models import (
    Airfield,
    Flight,
    Glider,
    Logsheet,
    Towplane,
    TowplaneChargeScheme,
    TowplaneChargeTier,
)
from members.models import Member
from siteconfig.models import (
    MembershipBillingRule,
    MembershipGliderRentalRule,
    MembershipStatus,
    SiteConfiguration,
)

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
        SiteConfiguration.objects.create(
            club_name="Test Club",
            domain_name="example.org",
            club_abbreviation="TC",
        )
        MembershipStatus.objects.get_or_create(
            name="Full Member", defaults={"is_active": True}
        )
        MembershipStatus.objects.get_or_create(
            name="Student Member", defaults={"is_active": True}
        )

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
        self.instructor = Member.objects.create(
            username="instructor1",
            membership_status="Full Member",
            instructor=True,
        )

        # Create airfield and logsheet
        self.airfield = Airfield.objects.create(identifier="KTEST", name="Test Field")

        self.logsheet = Logsheet.objects.create(
            log_date="2025-01-01", airfield=self.airfield, created_by=self.member
        )
        self.glider = Glider.objects.create(
            n_number="N100GL",
            model="ASK-21",
            club_owned=True,
            rental_rate=Decimal("12.00"),
        )

        # Create towplanes
        self.standard_towplane = Towplane.objects.create(
            name="Standard Tow", n_number="N123ST"
        )

        self.premium_towplane = Towplane.objects.create(
            name="Premium Tow", n_number="N456PT"
        )

        # No longer need global tow rates - all towplanes should have charge schemes

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

    def test_flight_without_scheme_returns_none(self):
        """Test flight returns None when no charge scheme exists."""
        flight = Flight.objects.create(
            logsheet=self.logsheet,
            pilot=self.member,
            towplane=self.standard_towplane,
            release_altitude=2000,
        )

        # Should return None when no charge scheme exists
        cost = flight.tow_cost_calculated
        self.assertIsNone(cost)

    def test_flight_with_inactive_scheme_returns_none(self):
        """Test flight returns None when towplane scheme is inactive."""
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

        # Should return None when scheme is inactive
        cost = flight.tow_cost_calculated
        self.assertIsNone(cost)

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

    def test_tow_discount_applies_when_billing_rules_enabled(self):
        """Tow discount should apply when site config enables billing rules."""
        config = SiteConfiguration.objects.first()
        self.assertIsNotNone(config)
        config.billing_rules_enabled = True
        config.save()

        student_status = MembershipStatus.objects.get(name="Student Member")
        MembershipBillingRule.objects.create(
            membership_status=student_status,
            tow_discount_percent=Decimal("25.00"),
        )

        student = Member.objects.create(
            username="student1", membership_status="Student Member"
        )
        flight = Flight.objects.create(
            logsheet=self.logsheet,
            pilot=student,
            towplane=self.premium_towplane,
            release_altitude=2000,
        )

        # Base cost: $40.00, discounted by 25% => $30.00
        self.assertEqual(flight.tow_cost_calculated, Decimal("30.00"))

    def test_default_discount_applies_when_no_status_rule_exists(self):
        """Default config discount should apply when no active status-specific rule exists."""
        config = SiteConfiguration.objects.first()
        self.assertIsNotNone(config)
        config.billing_rules_enabled = True
        config.default_tow_discount_percent = Decimal("10.00")
        config.save()

        flight = Flight.objects.create(
            logsheet=self.logsheet,
            pilot=self.member,
            towplane=self.premium_towplane,
            release_altitude=2000,
        )

        # Base cost: $40.00, default discount 10% => $36.00
        self.assertEqual(flight.tow_cost_calculated, Decimal("36.00"))

    def test_matrix_mode_uses_absolute_tow_hookup_and_rate_overrides(self):
        """Matrix mode should compose tow cost from per-status hookup and rate overrides."""
        config = SiteConfiguration.objects.first()
        self.assertIsNotNone(config)
        config.billing_rules_enabled = True
        config.billing_pricing_mode = "matrix"
        config.save()

        status = MembershipStatus.objects.get(name="Student Member")
        MembershipBillingRule.objects.create(
            membership_status=status,
            tow_hookup_fee_override=Decimal("5.00"),
            tow_rate_per_1000ft_override=Decimal("7.50"),
        )

        student = Member.objects.create(
            username="student2", membership_status="Student Member"
        )
        flight = Flight.objects.create(
            logsheet=self.logsheet,
            pilot=student,
            towplane=self.premium_towplane,
            release_altitude=2000,
        )

        # matrix: hookup $5 + ceil(2000/1000)*$7.50 = $20.00
        self.assertEqual(flight.tow_cost_calculated, Decimal("20.00"))

    def test_matrix_mode_applies_glider_rental_rate_override(self):
        """Matrix mode should use per-status absolute glider rental hourly override."""
        config = SiteConfiguration.objects.first()
        self.assertIsNotNone(config)
        config.billing_rules_enabled = True
        config.billing_pricing_mode = "matrix"
        config.save()

        status = MembershipStatus.objects.get(name="Student Member")
        MembershipBillingRule.objects.create(
            membership_status=status,
            glider_rental_rate_per_hour_override=Decimal("9.00"),
        )

        student = Member.objects.create(
            username="student3", membership_status="Student Member"
        )
        flight = Flight.objects.create(
            logsheet=self.logsheet,
            pilot=student,
            glider=self.glider,
            towplane=self.premium_towplane,
            release_altitude=2000,
            launch_time=time(9, 0),
            landing_time=time(10, 0),
        )

        # Override 1 hour @ $9.00
        self.assertEqual(flight.rental_cost_calculated, Decimal("9.00"))

    def test_matrix_mode_applies_flat_instruction_fee(self):
        """Matrix mode should apply per-flight instruction fee independent of duration."""
        config = SiteConfiguration.objects.first()
        self.assertIsNotNone(config)
        config.billing_rules_enabled = True
        config.billing_pricing_mode = "matrix"
        config.instructor_time_charges_enabled = True
        config.save()

        status = MembershipStatus.objects.get(name="Student Member")
        MembershipBillingRule.objects.create(
            membership_status=status,
            instruction_flat_fee_per_flight=Decimal("18.00"),
            charge_instruction_per_instructed_flight=True,
        )

        student = Member.objects.create(
            username="student4", membership_status="Student Member"
        )
        flight = Flight.objects.create(
            logsheet=self.logsheet,
            pilot=student,
            instructor=self.instructor,
            glider=self.glider,
            towplane=self.premium_towplane,
            release_altitude=2000,
            launch_time=time(9, 0),
            landing_time=time(9, 10),
        )
        long_flight = Flight.objects.create(
            logsheet=self.logsheet,
            pilot=student,
            instructor=self.instructor,
            glider=self.glider,
            towplane=self.premium_towplane,
            release_altitude=2000,
            launch_time=time(10, 0),
            landing_time=time(12, 0),
        )

        self.assertEqual(flight.instruction_fee_calculated, Decimal("18.00"))
        self.assertEqual(long_flight.instruction_fee_calculated, Decimal("18.00"))

    def test_minimum_billable_rental_minutes_floor_applies(self):
        """Rental billing should floor duration to configured minimum minutes."""
        config = SiteConfiguration.objects.first()
        self.assertIsNotNone(config)
        config.billing_rules_enabled = True
        config.minimum_billable_rental_minutes = 20
        config.save()

        flight = Flight.objects.create(
            logsheet=self.logsheet,
            pilot=self.member,
            glider=self.glider,
            towplane=self.premium_towplane,
            release_altitude=2000,
            launch_time=time(9, 0),
            landing_time=time(9, 10),
        )

        # Glider rate $12/hr with 20-minute floor => $4.00
        self.assertEqual(flight.rental_cost_calculated, Decimal("4.00"))

    def test_minimum_billable_rental_minutes_ignored_when_billing_rules_disabled(self):
        """Minimum rental floor should not apply when billing rules are disabled."""
        config = SiteConfiguration.objects.first()
        self.assertIsNotNone(config)
        config.billing_rules_enabled = False
        config.minimum_billable_rental_minutes = 20
        config.save()

        flight = Flight.objects.create(
            logsheet=self.logsheet,
            pilot=self.member,
            glider=self.glider,
            towplane=self.premium_towplane,
            release_altitude=2000,
            launch_time=time(9, 0),
            landing_time=time(9, 10),
        )

        # Base behavior with 10-minute flight and $12/hr rate => $2.00.
        self.assertEqual(flight.rental_cost_calculated, Decimal("2.00"))

    def test_matrix_mode_glider_specific_override_precedence(self):
        """Per-glider status override should take precedence over status-wide hourly override."""
        config = SiteConfiguration.objects.first()
        self.assertIsNotNone(config)
        config.billing_rules_enabled = True
        config.billing_pricing_mode = "matrix"
        config.save()

        status = MembershipStatus.objects.get(name="Student Member")
        MembershipBillingRule.objects.create(
            membership_status=status,
            glider_rental_rate_per_hour_override=Decimal("9.00"),
        )

        free_glider = Glider.objects.create(
            n_number="N777JR",
            model="Junior Waived",
            club_owned=True,
            rental_rate=Decimal("12.00"),
        )
        paid_glider = Glider.objects.create(
            n_number="N888JR",
            model="Junior Paid",
            club_owned=True,
            rental_rate=Decimal("12.00"),
        )

        MembershipGliderRentalRule.objects.create(
            membership_status=status,
            glider=free_glider,
            hourly_rate_override=Decimal("0.00"),
        )

        student = Member.objects.create(
            username="student5", membership_status="Student Member"
        )
        waived_flight = Flight.objects.create(
            logsheet=self.logsheet,
            pilot=student,
            glider=free_glider,
            towplane=self.premium_towplane,
            release_altitude=2000,
            launch_time=time(9, 0),
            landing_time=time(10, 0),
        )
        paid_flight = Flight.objects.create(
            logsheet=self.logsheet,
            pilot=student,
            glider=paid_glider,
            towplane=self.premium_towplane,
            release_altitude=2000,
            launch_time=time(10, 0),
            landing_time=time(11, 0),
        )

        self.assertEqual(waived_flight.rental_cost_calculated, Decimal("0.00"))
        self.assertEqual(paid_flight.rental_cost_calculated, Decimal("9.00"))
