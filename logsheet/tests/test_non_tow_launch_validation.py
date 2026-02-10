"""
Tests for non-tow launch method validation (self-launch, winch, other).

Validates that flights with launch_method != 'tow' do not require:
- Tow pilot
- Towplane (or only require virtual towplanes)
- Tach times/fuel data in closeout

Issue #623: Logsheet: Self-Launch or Winch, no towpilots
"""

from datetime import date, time

import pytest
from django.contrib.messages import get_messages

from logsheet.models import (
    Airfield,
    Flight,
    Glider,
    Logsheet,
    LogsheetCloseout,
    LogsheetPayment,
    Towplane,
    TowplaneCloseout,
)
from members.models import Member


@pytest.fixture
def airfield(db):
    """Create test airfield."""
    return Airfield.objects.create(name="Test Field", identifier="TST")


@pytest.fixture
def glider(db):
    """Create test glider."""
    return Glider.objects.create(
        make="Test",
        model="Glider",
        n_number="G-TEST",
        club_owned=True,
        rental_rate=50.00,
    )


@pytest.fixture
def towplane(db):
    """Create regular towplane."""
    return Towplane.objects.create(
        name="Test Towplane",
        n_number="N12345",
        is_active=True,
        club_owned=True,
    )


@pytest.fixture
def virtual_towplane_self(db):
    """Create virtual towplane for self-launch."""
    return Towplane.objects.create(
        name="Self-Launch",
        n_number="SELF",
        is_active=True,
        club_owned=False,
    )


@pytest.fixture
def virtual_towplane_winch(db):
    """Create virtual towplane for winch."""
    return Towplane.objects.create(
        name="Winch",
        n_number="WINCH",
        is_active=True,
        club_owned=False,
    )


@pytest.fixture
def virtual_towplane_other(db):
    """Create virtual towplane for other."""
    return Towplane.objects.create(
        name="Other",
        n_number="OTHER",
        is_active=True,
        club_owned=False,
    )


@pytest.fixture
def pilot(db):
    """Create pilot member."""
    return Member.objects.create(
        username="pilot",
        first_name="Test",
        last_name="Pilot",
        membership_status="Full Member",
    )


@pytest.fixture
def tow_pilot(db):
    """Create tow pilot member."""
    return Member.objects.create(
        username="towpilot",
        first_name="Tow",
        last_name="Pilot",
        membership_status="Full Member",
        towpilot=True,
    )


@pytest.fixture
def duty_officer(db):
    """Create duty officer member."""
    return Member.objects.create(
        username="do",
        first_name="Duty",
        last_name="Officer",
        membership_status="Full Member",
        duty_officer=True,
    )


@pytest.fixture
def duty_instructor(db):
    """Create duty instructor member."""
    return Member.objects.create(
        username="instructor",
        first_name="Duty",
        last_name="Instructor",
        membership_status="Full Member",
        instructor=True,
    )


@pytest.fixture
def logsheet(db, airfield, pilot, duty_officer, duty_instructor):
    """Create test logsheet."""
    return Logsheet.objects.create(
        log_date=date.today(),
        airfield=airfield,
        created_by=pilot,
        duty_officer=duty_officer,
        duty_instructor=duty_instructor,
    )


class TestFlightRequiresTow:
    """Test Flight.requires_tow property."""

    def test_towplane_launch_requires_tow(self, db, logsheet, pilot, glider):
        """Towplane launches require tow pilot and towplane."""
        flight = Flight.objects.create(
            logsheet=logsheet,
            pilot=pilot,
            glider=glider,
            launch_method=Flight.LaunchMethod.TOWPLANE,
        )
        assert flight.requires_tow is True

    def test_winch_launch_does_not_require_tow(self, db, logsheet, pilot, glider):
        """Winch launches do not require tow pilot."""
        flight = Flight.objects.create(
            logsheet=logsheet,
            pilot=pilot,
            glider=glider,
            launch_method=Flight.LaunchMethod.WINCH,
        )
        assert flight.requires_tow is False

    def test_self_launch_does_not_require_tow(self, db, logsheet, pilot, glider):
        """Self-launches do not require tow pilot."""
        flight = Flight.objects.create(
            logsheet=logsheet,
            pilot=pilot,
            glider=glider,
            launch_method=Flight.LaunchMethod.SELF,
        )
        assert flight.requires_tow is False

    def test_other_launch_does_not_require_tow(self, db, logsheet, pilot, glider):
        """Other launches do not require tow pilot."""
        flight = Flight.objects.create(
            logsheet=logsheet,
            pilot=pilot,
            glider=glider,
            launch_method=Flight.LaunchMethod.OTHER,
        )
        assert flight.requires_tow is False

    def test_virtual_towplane_overrides_launch_method(
        self, db, logsheet, pilot, glider, virtual_towplane_self
    ):
        """Flight with virtual towplane (SELF) doesn't require tow pilot, even with default launch_method.

        This tests the real-world scenario where a user selects "Self-Launch (SELF)"
        as the towplane in the UI, but launch_method remains at its default of "tow".
        """
        flight = Flight.objects.create(
            logsheet=logsheet,
            pilot=pilot,
            glider=glider,
            launch_method=Flight.LaunchMethod.TOWPLANE,  # Default value
            towplane=virtual_towplane_self,  # But virtual towplane selected
        )
        assert flight.requires_tow is False


class TestFlightIncomplete:
    """Test Flight.is_incomplete() with different launch methods."""

    def test_towplane_incomplete_without_tow_pilot(
        self, db, logsheet, pilot, glider, towplane
    ):
        """Towplane launch is incomplete without tow pilot."""
        flight = Flight.objects.create(
            logsheet=logsheet,
            pilot=pilot,
            glider=glider,
            launch_method=Flight.LaunchMethod.TOWPLANE,
            launch_time=time(10, 0),
            landing_time=time(11, 0),
            release_altitude=3000,
            towplane=towplane,
            # No tow_pilot
        )
        assert flight.is_incomplete() is True
        assert "tow pilot" in flight.get_missing_fields()

    def test_winch_complete_without_tow_pilot(
        self, db, logsheet, pilot, glider, virtual_towplane_winch
    ):
        """Winch launch is complete without tow pilot."""
        flight = Flight.objects.create(
            logsheet=logsheet,
            pilot=pilot,
            glider=glider,
            launch_method=Flight.LaunchMethod.WINCH,
            launch_time=time(10, 0),
            landing_time=time(11, 0),
            release_altitude=1000,
            towplane=virtual_towplane_winch,
            # No tow_pilot - this is OK for winch
        )
        assert flight.is_incomplete() is False
        assert "tow pilot" not in flight.get_missing_fields()
        assert "towplane" not in flight.get_missing_fields()

    def test_self_launch_complete_without_tow_pilot(
        self, db, logsheet, pilot, glider, virtual_towplane_self
    ):
        """Self-launch is complete without tow pilot."""
        flight = Flight.objects.create(
            logsheet=logsheet,
            pilot=pilot,
            glider=glider,
            launch_method=Flight.LaunchMethod.SELF,
            launch_time=time(10, 0),
            landing_time=time(11, 0),
            release_altitude=0,  # Self-launch typically has 0 release altitude
            towplane=virtual_towplane_self,
            # No tow_pilot - this is OK for self-launch
        )
        assert flight.is_incomplete() is False
        assert "tow pilot" not in flight.get_missing_fields()


class TestTowplaneIsVirtual:
    """Test Towplane.is_virtual property."""

    def test_regular_towplane_not_virtual(self, db, towplane):
        """Regular towplane with N-number is not virtual."""
        assert towplane.is_virtual is False

    def test_self_launch_is_virtual(self, db, virtual_towplane_self):
        """SELF towplane is virtual."""
        assert virtual_towplane_self.is_virtual is True

    def test_winch_is_virtual(self, db, virtual_towplane_winch):
        """WINCH towplane is virtual."""
        assert virtual_towplane_winch.is_virtual is True

    def test_other_is_virtual(self, db, virtual_towplane_other):
        """OTHER towplane is virtual."""
        assert virtual_towplane_other.is_virtual is True

    def test_virtual_case_insensitive(self, db):
        """Virtual N-numbers are case-insensitive."""
        towplane_lower = Towplane.objects.create(
            name="Self", n_number="self", is_active=True
        )
        towplane_mixed = Towplane.objects.create(
            name="Self", n_number="SeLf", is_active=True
        )
        assert towplane_lower.is_virtual is True
        assert towplane_mixed.is_virtual is True


@pytest.mark.django_db
class TestFinalizationWithNonTowFlights:
    """Test logsheet finalization with non-tow launch methods."""

    def test_finalization_without_logsheet_tow_pilot_when_no_tow_flights(
        self,
        client,
        logsheet,
        pilot,
        glider,
        virtual_towplane_winch,
        duty_officer,
        duty_instructor,
    ):
        """Can finalize logsheet without tow_pilot if all flights are winch/self/other."""
        # Create winch flight without tow pilot
        Flight.objects.create(
            logsheet=logsheet,
            pilot=pilot,
            glider=glider,
            launch_method=Flight.LaunchMethod.WINCH,
            launch_time=time(10, 0),
            landing_time=time(11, 0),
            release_altitude=1000,
            towplane=virtual_towplane_winch,
        )

        # Create closeout (required for finalization)
        LogsheetCloseout.objects.create(logsheet=logsheet)

        # Create payment
        LogsheetPayment.objects.create(
            logsheet=logsheet, member=pilot, payment_method="cash"
        )

        # Log in as duty officer
        client.force_login(duty_officer)

        # Attempt finalization - should succeed even without logsheet.tow_pilot
        client.post(
            f"/logsheet/manage/{logsheet.pk}/", {"finalize": "true"}, follow=True
        )

        logsheet.refresh_from_db()
        assert logsheet.finalized is True

    def test_finalization_requires_tow_pilot_when_tow_flights_exist(
        self,
        client,
        logsheet,
        pilot,
        glider,
        towplane,
        tow_pilot,
        duty_officer,
        duty_instructor,
    ):
        """Finalization requires logsheet.tow_pilot if any towplane flights exist."""
        # Create towplane flight
        Flight.objects.create(
            logsheet=logsheet,
            pilot=pilot,
            glider=glider,
            launch_method=Flight.LaunchMethod.TOWPLANE,
            launch_time=time(10, 0),
            landing_time=time(11, 0),
            release_altitude=3000,
            towplane=towplane,
            tow_pilot=tow_pilot,
        )

        # Create closeout
        LogsheetCloseout.objects.create(logsheet=logsheet)

        # Create towplane closeout
        TowplaneCloseout.objects.create(
            logsheet=logsheet,
            towplane=towplane,
            start_tach=100.0,
            end_tach=101.5,
            fuel_added=10.0,
        )

        # Create payment
        LogsheetPayment.objects.create(
            logsheet=logsheet, member=pilot, payment_method="cash"
        )

        # Remove logsheet tow pilot
        logsheet.tow_pilot = None
        logsheet.save()

        # Log in as duty officer
        client.force_login(duty_officer)

        # Attempt finalization - should fail without tow_pilot
        response = client.post(
            f"/logsheet/manage/{logsheet.pk}/", {"finalize": "true"}, follow=True
        )

        logsheet.refresh_from_db()
        assert logsheet.finalized is False

        # Check error message
        messages = list(get_messages(response.wsgi_request))
        assert any("Missing duty crew" in str(m) for m in messages)
        assert any("Tow Pilot" in str(m) for m in messages)


@pytest.mark.django_db
class TestCloseoutValidationWithVirtualTowplanes:
    """Test that virtual towplanes (SELF, WINCH, OTHER) don't require closeout data."""

    def test_virtual_towplane_skips_closeout_validation(
        self,
        client,
        logsheet,
        pilot,
        glider,
        virtual_towplane_winch,
        duty_officer,
        duty_instructor,
    ):
        """Virtual towplanes don't need closeout entries."""
        # Create winch flight
        Flight.objects.create(
            logsheet=logsheet,
            pilot=pilot,
            glider=glider,
            launch_method=Flight.LaunchMethod.WINCH,
            launch_time=time(10, 0),
            landing_time=time(11, 0),
            release_altitude=1000,
            towplane=virtual_towplane_winch,
        )

        # Create closeout
        LogsheetCloseout.objects.create(logsheet=logsheet)

        # Create payment
        LogsheetPayment.objects.create(
            logsheet=logsheet, member=pilot, payment_method="cash"
        )

        # NO TowplaneCloseout created - should still finalize

        # Log in as duty officer
        client.force_login(duty_officer)

        # Attempt finalization - should succeed without towplane closeout
        client.post(
            f"/logsheet/manage/{logsheet.pk}/", {"finalize": "true"}, follow=True
        )

        logsheet.refresh_from_db()
        assert logsheet.finalized is True

    def test_regular_towplane_requires_closeout_validation(
        self,
        client,
        logsheet,
        pilot,
        glider,
        towplane,
        tow_pilot,
        duty_officer,
        duty_instructor,
    ):
        """Regular towplanes require closeout entries."""
        # Set logsheet tow pilot
        logsheet.tow_pilot = tow_pilot
        logsheet.save()

        # Create towplane flight
        Flight.objects.create(
            logsheet=logsheet,
            pilot=pilot,
            glider=glider,
            launch_method=Flight.LaunchMethod.TOWPLANE,
            launch_time=time(10, 0),
            landing_time=time(11, 0),
            release_altitude=3000,
            towplane=towplane,
            tow_pilot=tow_pilot,
        )

        # Create closeout
        LogsheetCloseout.objects.create(logsheet=logsheet)

        # Create payment
        LogsheetPayment.objects.create(
            logsheet=logsheet, member=pilot, payment_method="cash"
        )

        # NO TowplaneCloseout created - finalization should fail

        # Log in as duty officer
        client.force_login(duty_officer)

        # Attempt finalization - should fail without towplane closeout
        response = client.post(
            f"/logsheet/manage/{logsheet.pk}/", {"finalize": "true"}, follow=True
        )

        logsheet.refresh_from_db()
        assert logsheet.finalized is False

        # Check error message
        messages = list(get_messages(response.wsgi_request))
        assert any("Missing closeout data" in str(m) for m in messages)
