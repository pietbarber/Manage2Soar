"""
Tests for ChargeableItem and MemberCharge functionality.

Issue #66: Aerotow retrieve fees
Issue #413: Miscellaneous charges
"""

from datetime import date, time
from decimal import Decimal

from django.test import TestCase

from logsheet.models import (
    Airfield,
    Flight,
    Glider,
    Logsheet,
    MemberCharge,
    Towplane,
    TowplaneChargeScheme,
    TowplaneChargeTier,
)
from members.models import Member
from siteconfig.models import ChargeableItem, MembershipStatus, SiteConfiguration


class ChargeableItemModelTestCase(TestCase):
    """Test ChargeableItem model functionality."""

    def test_create_each_item(self):
        """Test creating a per-item chargeable item."""
        item = ChargeableItem.objects.create(
            name="T-Shirt Large",
            price=Decimal("25.00"),
            unit=ChargeableItem.UnitType.EACH,
            allows_decimal_quantity=False,
        )
        self.assertEqual(item.name, "T-Shirt Large")
        self.assertEqual(item.price, Decimal("25.00"))
        self.assertEqual(item.unit, ChargeableItem.UnitType.EACH)
        self.assertFalse(item.allows_decimal_quantity)
        self.assertTrue(item.is_active)

    def test_create_hourly_item(self):
        """Test creating a per-hour chargeable item."""
        item = ChargeableItem.objects.create(
            name="Aerotow Retrieve",
            price=Decimal("120.00"),
            unit=ChargeableItem.UnitType.HOUR,
            allows_decimal_quantity=True,
        )
        self.assertEqual(item.unit, ChargeableItem.UnitType.HOUR)
        self.assertTrue(item.allows_decimal_quantity)

    def test_item_str_representation(self):
        """Test string representation of chargeable items."""
        each_item = ChargeableItem.objects.create(
            name="Logbook",
            price=Decimal("15.00"),
            unit=ChargeableItem.UnitType.EACH,
        )
        self.assertEqual(str(each_item), "Logbook ($15.00)")

        hour_item = ChargeableItem.objects.create(
            name="Towplane Retrieve",
            price=Decimal("120.00"),
            unit=ChargeableItem.UnitType.HOUR,
        )
        self.assertEqual(str(hour_item), "Towplane Retrieve ($120.00/hour)")


class MemberChargeModelTestCase(TestCase):
    """Test MemberCharge model functionality."""

    def setUp(self):
        """Set up test data for MemberCharge tests."""
        # Create membership status
        MembershipStatus.objects.get_or_create(
            name="Full Member", defaults={"is_active": True}
        )
        MembershipStatus.objects.get_or_create(
            name="Inactive", defaults={"is_active": False}
        )

        # Create site config
        SiteConfiguration.objects.all().delete()
        SiteConfiguration.objects.create(
            club_name="Test Club",
            domain_name="test.org",
            club_abbreviation="TC",
        )

        # Create users and members
        self.member1 = Member.objects.create_user(
            username="chargepilot1@test.com",
            email="chargepilot1@test.com",
            first_name="John",
            last_name="Doe",
        )
        self.member1.membership_status = "Full Member"
        self.member1.save()

        self.member2 = Member.objects.create_user(
            username="chargedo1@test.com",
            email="chargedo1@test.com",
            first_name="Jane",
            last_name="Smith",
        )
        self.member2.membership_status = "Full Member"
        self.member2.duty_officer = True
        self.member2.save()

        # Create airfield and logsheet
        self.airfield = Airfield.objects.create(
            name="Test Airfield",
            identifier="CHARGE",
        )
        self.logsheet = Logsheet.objects.create(
            log_date=date.today(),
            airfield=self.airfield,
            created_by=self.member2,
        )

        # Create chargeable items
        self.tshirt = ChargeableItem.objects.create(
            name="T-Shirt Large",
            price=Decimal("25.00"),
            unit=ChargeableItem.UnitType.EACH,
        )
        self.retrieve = ChargeableItem.objects.create(
            name="Aerotow Retrieve",
            price=Decimal("120.00"),
            unit=ChargeableItem.UnitType.HOUR,
            allows_decimal_quantity=True,
        )

    def test_create_member_charge(self):
        """Test creating a simple member charge."""
        charge = MemberCharge.objects.create(
            member=self.member1,
            chargeable_item=self.tshirt,
            quantity=Decimal("2.00"),
            unit_price=self.tshirt.price,
            date=date.today(),
            logsheet=self.logsheet,
            entered_by=self.member2,
        )
        # save() should auto-calculate total_price
        self.assertEqual(charge.total_price, Decimal("50.00"))

    def test_member_charge_snapshots_price(self):
        """Test that unit_price is snapshotted at creation time."""
        original_price = self.tshirt.price
        charge = MemberCharge.objects.create(
            member=self.member1,
            chargeable_item=self.tshirt,
            quantity=Decimal("1.00"),
            unit_price=original_price,
            date=date.today(),
            entered_by=self.member2,
        )

        # Change the catalog price
        self.tshirt.price = Decimal("30.00")
        self.tshirt.save()

        # Refresh charge from db
        charge.refresh_from_db()
        # The charge's unit_price should remain the original
        self.assertEqual(charge.unit_price, original_price)
        self.assertEqual(charge.total_price, Decimal("25.00"))

    def test_decimal_quantity_for_tach_time(self):
        """Test decimal quantity for retrieve tach time."""
        charge = MemberCharge.objects.create(
            member=self.member1,
            chargeable_item=self.retrieve,
            quantity=Decimal("1.80"),  # 1.8 hours
            unit_price=self.retrieve.price,
            date=date.today(),
            notes="Retrieve from XYZ field",
            entered_by=self.member2,
        )
        # 1.8 * 120 = 216
        self.assertEqual(charge.total_price, Decimal("216.00"))

    def test_is_locked_property(self):
        """Test that charges tied to finalized logsheets are locked."""
        charge = MemberCharge.objects.create(
            member=self.member1,
            chargeable_item=self.tshirt,
            quantity=Decimal("1.00"),
            unit_price=self.tshirt.price,
            date=date.today(),
            logsheet=self.logsheet,
            entered_by=self.member2,
        )
        self.assertFalse(charge.is_locked)

        # Finalize the logsheet
        self.logsheet.finalized = True
        self.logsheet.save()

        charge.refresh_from_db()
        self.assertTrue(charge.is_locked)


class FlightFreeFlagsTestCase(TestCase):
    """Test free_tow, free_rental, and is_retrieve flags on flights."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data for flight flag tests."""
        # Create membership status
        MembershipStatus.objects.get_or_create(
            name="Full Member", defaults={"is_active": True}
        )

        # Create site config
        SiteConfiguration.objects.all().delete()
        cls.config = SiteConfiguration.objects.create(
            club_name="Test Club",
            domain_name="test.org",
            club_abbreviation="TC",
            waive_tow_fee_on_retrieve=False,
            waive_rental_fee_on_retrieve=False,
        )

        # Create member (Member extends AbstractUser)
        cls.member = Member.objects.create_user(
            username="pilot@test.com",
            email="pilot@test.com",
            first_name="Test",
            last_name="Pilot",
        )
        cls.member.membership_status = "Full Member"
        cls.member.save()

        # Create airfield
        cls.airfield = Airfield.objects.create(
            name="Test Airfield",
            identifier="TEST",
        )

        # Create logsheet
        cls.logsheet = Logsheet.objects.create(
            log_date=date.today(),
            airfield=cls.airfield,
            created_by=cls.member,
        )

        # Create towplane with charge scheme
        cls.towplane = Towplane.objects.create(
            name="Test Pawnee",
            n_number="N123TP",
            is_active=True,
        )
        cls.scheme = TowplaneChargeScheme.objects.create(
            towplane=cls.towplane,
            name="Test Scheme",
            hookup_fee=Decimal("10.00"),
            is_active=True,
        )
        TowplaneChargeTier.objects.create(
            charge_scheme=cls.scheme,
            altitude_start=0,
            altitude_end=3000,
            rate_type="per_100ft",
            rate_amount=Decimal("5.00"),
            is_active=True,
        )

        # Create glider
        cls.glider = Glider.objects.create(
            make="Schleicher",
            model="ASK-21",
            n_number="N456GL",
            is_active=True,
            rental_rate=Decimal("30.00"),  # $30/hour
        )

    def test_free_tow_zeroes_tow_cost(self):
        """Test that free_tow=True results in $0 tow cost."""
        flight = Flight.objects.create(
            logsheet=self.logsheet,
            pilot=self.member,
            glider=self.glider,
            towplane=self.towplane,
            release_altitude=2000,
            launch_time=time(10, 0),
            landing_time=time(10, 30),
            free_tow=True,
        )
        self.assertEqual(flight.tow_cost, Decimal("0.00"))

    def test_free_rental_zeroes_rental_cost(self):
        """Test that free_rental=True results in $0 rental cost."""
        flight = Flight.objects.create(
            logsheet=self.logsheet,
            pilot=self.member,
            glider=self.glider,
            towplane=self.towplane,
            release_altitude=2000,
            launch_time=time(10, 0),
            landing_time=time(11, 0),  # 1 hour
            free_rental=True,
        )
        self.assertEqual(flight.rental_cost, Decimal("0.00"))

    def test_normal_flight_has_costs(self):
        """Test that normal flights have calculated costs."""
        flight = Flight.objects.create(
            logsheet=self.logsheet,
            pilot=self.member,
            glider=self.glider,
            towplane=self.towplane,
            release_altitude=2000,
            launch_time=time(10, 0),
            landing_time=time(11, 0),  # 1 hour
        )
        # Tow: $10 hookup + (2000/100 * $5) = $10 + $100 = $110
        self.assertEqual(flight.tow_cost, Decimal("110.00"))
        # Rental: 1 hour * $30/hour = $30
        self.assertEqual(flight.rental_cost, Decimal("30.00"))

    def test_retrieve_with_waive_tow_config(self):
        """Test that is_retrieve=True with config.waive_tow_fee_on_retrieve zeroes tow."""
        # Enable waiver
        self.config.waive_tow_fee_on_retrieve = True
        self.config.save()

        flight = Flight.objects.create(
            logsheet=self.logsheet,
            pilot=self.member,
            glider=self.glider,
            towplane=self.towplane,
            release_altitude=2000,
            launch_time=time(10, 0),
            landing_time=time(10, 30),
            is_retrieve=True,
        )
        self.assertEqual(flight.tow_cost, Decimal("0.00"))
        # Rental should still be charged (waive_rental_fee_on_retrieve is False)
        self.assertGreater(flight.rental_cost, Decimal("0.00"))

    def test_retrieve_with_waive_rental_config(self):
        """Test that is_retrieve=True with config.waive_rental_fee_on_retrieve zeroes rental."""
        # Enable waiver
        self.config.waive_rental_fee_on_retrieve = True
        self.config.save()

        flight = Flight.objects.create(
            logsheet=self.logsheet,
            pilot=self.member,
            glider=self.glider,
            towplane=self.towplane,
            release_altitude=2000,
            launch_time=time(10, 0),
            landing_time=time(11, 0),
            is_retrieve=True,
        )
        self.assertEqual(flight.rental_cost, Decimal("0.00"))
        # Tow should still be charged (waive_tow_fee_on_retrieve is False)
        self.assertGreater(flight.tow_cost, Decimal("0.00"))

    def test_retrieve_without_waiver_has_normal_costs(self):
        """Test that is_retrieve=True without waivers still charges normally."""
        # Ensure waivers are disabled
        self.config.waive_tow_fee_on_retrieve = False
        self.config.waive_rental_fee_on_retrieve = False
        self.config.save()

        flight = Flight.objects.create(
            logsheet=self.logsheet,
            pilot=self.member,
            glider=self.glider,
            towplane=self.towplane,
            release_altitude=2000,
            launch_time=time(10, 0),
            landing_time=time(11, 0),
            is_retrieve=True,
        )
        # Both should be charged
        self.assertGreater(flight.tow_cost, Decimal("0.00"))
        self.assertGreater(flight.rental_cost, Decimal("0.00"))
