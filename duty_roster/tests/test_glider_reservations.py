"""
Tests for the Glider Reservation System (Issue #410)

Tests cover:
- GliderReservation model
- Reservation creation, validation, and cancellation
- Yearly reservation limits
- SiteConfiguration integration
- Form validation
- Views and URLs
"""

from datetime import date, timedelta
from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from duty_roster.forms import GliderReservationCancelForm, GliderReservationForm
from duty_roster.models import GliderReservation
from logsheet.models import Glider, MaintenanceIssue
from members.models import Member
from siteconfig.models import SiteConfiguration


@pytest.fixture
def site_config(db):
    """Create a SiteConfiguration with reservations enabled."""
    config = SiteConfiguration.objects.first()
    if not config:
        config = SiteConfiguration.objects.create(
            club_name="Test Club",
            domain_name="test.com",
            club_abbreviation="TC",
        )
    config.allow_glider_reservations = True
    config.allow_two_seater_reservations = True
    config.max_reservations_per_year = 3
    config.save()
    return config


@pytest.fixture
def member(db, django_user_model):
    """Create an active member for testing."""
    user = django_user_model.objects.create_user(
        username="testmember",
        email="test@example.com",
        password="testpass123",
        first_name="Test",
        last_name="Member",
        membership_status="Full Member",
    )
    return user


@pytest.fixture
def glider(db):
    """Create a test glider."""
    return Glider.objects.create(
        make="Schleicher",
        model="ASK-21",
        n_number="N123AB",
        competition_number="21",
        seats=2,
        is_active=True,
        club_owned=True,
    )


@pytest.fixture
def single_seat_glider(db):
    """Create a single-seat test glider."""
    return Glider.objects.create(
        make="Schempp-Hirth",
        model="Discus",
        n_number="N456CD",
        competition_number="DS",
        seats=1,
        is_active=True,
        club_owned=True,
    )


@pytest.fixture
def private_glider(db):
    """Create a privately-owned glider."""
    return Glider.objects.create(
        make="Schleicher",
        model="ASW-27",
        n_number="N789EF",
        competition_number="27",
        seats=1,
        is_active=True,
        club_owned=False,  # Private
    )


@pytest.fixture
def future_date():
    """Return a date in the future."""
    return timezone.now().date() + timedelta(days=7)


class TestGliderReservationModel:
    """Tests for the GliderReservation model."""

    def test_create_reservation(self, site_config, member, glider, future_date):
        """Test creating a basic reservation."""
        reservation = GliderReservation.objects.create(
            member=member,
            glider=glider,
            date=future_date,
            reservation_type="solo",
            time_preference="morning",
        )
        assert reservation.pk is not None
        assert reservation.status == "confirmed"
        assert (
            str(reservation)
            == f"{member.full_display_name} - {glider} on {future_date}"
        )

    def test_is_active_property(self, site_config, member, glider, future_date):
        """Test the is_active property."""
        reservation = GliderReservation.objects.create(
            member=member,
            glider=glider,
            date=future_date,
            reservation_type="solo",
            time_preference="morning",
        )
        assert reservation.is_active is True

        # Cancelled reservation is not active
        reservation.status = "cancelled"
        reservation.save()
        assert reservation.is_active is False

    def test_is_trainer_property(
        self, site_config, member, glider, single_seat_glider, future_date
    ):
        """Test the is_trainer property."""
        # Two-seater is a trainer
        res_two_seat = GliderReservation.objects.create(
            member=member,
            glider=glider,  # 2-seater
            date=future_date,
            reservation_type="solo",
            time_preference="morning",
        )
        assert res_two_seat.is_trainer is True

        # Single-seater is not a trainer
        res_single = GliderReservation.objects.create(
            member=member,
            glider=single_seat_glider,
            date=future_date + timedelta(days=1),
            reservation_type="solo",
            time_preference="morning",
        )
        assert res_single.is_trainer is False

    def test_yearly_count(self, site_config, member, glider, future_date):
        """Test yearly reservation count tracking."""
        # No reservations initially
        assert GliderReservation.get_member_yearly_count(member) == 0

        # Create a reservation
        GliderReservation.objects.create(
            member=member,
            glider=glider,
            date=future_date,
            reservation_type="solo",
            time_preference="morning",
        )
        assert GliderReservation.get_member_yearly_count(member) == 1

        # Cancelled reservations don't count
        cancelled_res = GliderReservation.objects.create(
            member=member,
            glider=glider,
            date=future_date + timedelta(days=1),
            reservation_type="solo",
            time_preference="afternoon",
            status="cancelled",
        )
        assert GliderReservation.get_member_yearly_count(member) == 1

    def test_reservations_by_year(self, site_config, member, glider, future_date):
        """Test getting reservations grouped by year."""
        # Create reservations
        GliderReservation.objects.create(
            member=member,
            glider=glider,
            date=future_date,
            reservation_type="solo",
            time_preference="morning",
        )
        yearly = GliderReservation.get_reservations_by_year(member)
        assert future_date.year in yearly
        assert yearly[future_date.year] == 1

    def test_can_member_reserve_with_limit(
        self, site_config, member, glider, future_date
    ):
        """Test reservation limit enforcement."""
        # Can reserve initially
        can_reserve, message = GliderReservation.can_member_reserve(member)
        assert can_reserve is True

        # Create max reservations
        for i in range(site_config.max_reservations_per_year):
            GliderReservation.objects.create(
                member=member,
                glider=glider,
                date=future_date + timedelta(days=i),
                reservation_type="solo",
                time_preference="morning",
            )

        # Now at limit
        can_reserve, message = GliderReservation.can_member_reserve(member)
        assert can_reserve is False
        assert "limit" in message.lower()

    def test_can_member_reserve_unlimited(
        self, site_config, member, glider, future_date
    ):
        """Test unlimited reservations when max is 0."""
        site_config.max_reservations_per_year = 0  # Unlimited
        site_config.save()

        # Create many reservations
        for i in range(10):
            GliderReservation.objects.create(
                member=member,
                glider=glider,
                date=future_date + timedelta(days=i),
                reservation_type="solo",
                time_preference="morning",
            )

        # Can still reserve
        can_reserve, message = GliderReservation.can_member_reserve(member)
        assert can_reserve is True

    def test_reservations_disabled(self, site_config, member):
        """Test when reservations are disabled."""
        site_config.allow_glider_reservations = False
        site_config.save()

        can_reserve, message = GliderReservation.can_member_reserve(member)
        assert can_reserve is False
        assert "disabled" in message.lower()

    def test_cancel_reservation(self, site_config, member, glider, future_date):
        """Test cancelling a reservation."""
        reservation = GliderReservation.objects.create(
            member=member,
            glider=glider,
            date=future_date,
            reservation_type="solo",
            time_preference="morning",
        )
        assert reservation.status == "confirmed"

        reservation.cancel(reason="Weather forecast is bad")
        reservation.refresh_from_db()

        assert reservation.status == "cancelled"
        assert reservation.cancellation_reason == "Weather forecast is bad"
        assert reservation.cancelled_at is not None


class TestGliderReservationValidation:
    """Tests for reservation validation."""

    def test_cannot_reserve_grounded_glider(
        self, site_config, member, glider, future_date
    ):
        """Test that grounded gliders cannot be reserved."""
        # Ground the glider
        MaintenanceIssue.objects.create(
            glider=glider,
            description="Engine problem",
            grounded=True,
            resolved=False,
        )

        reservation = GliderReservation(
            member=member,
            glider=glider,
            date=future_date,
            reservation_type="solo",
            time_preference="morning",
        )

        with pytest.raises(ValidationError) as exc_info:
            reservation.clean()
        assert "grounded" in str(exc_info.value).lower()

    def test_cannot_reserve_private_glider(
        self, site_config, member, private_glider, future_date
    ):
        """Test that private gliders cannot be reserved."""
        reservation = GliderReservation(
            member=member,
            glider=private_glider,
            date=future_date,
            reservation_type="solo",
            time_preference="morning",
        )

        with pytest.raises(ValidationError) as exc_info:
            reservation.clean()
        assert "privately owned" in str(exc_info.value).lower()

    def test_cannot_reserve_inactive_glider(
        self, site_config, member, glider, future_date
    ):
        """Test that inactive gliders cannot be reserved."""
        glider.is_active = False
        glider.save()

        reservation = GliderReservation(
            member=member,
            glider=glider,
            date=future_date,
            reservation_type="solo",
            time_preference="morning",
        )

        with pytest.raises(ValidationError) as exc_info:
            reservation.clean()
        assert "not currently active" in str(exc_info.value).lower()

    def test_two_seater_reservations_disabled(
        self, site_config, member, glider, future_date
    ):
        """Test that two-seater reservations can be disabled."""
        site_config.allow_two_seater_reservations = False
        site_config.save()

        reservation = GliderReservation(
            member=member,
            glider=glider,  # 2-seater
            date=future_date,
            reservation_type="solo",
            time_preference="morning",
        )

        with pytest.raises(ValidationError) as exc_info:
            reservation.clean()
        assert "two-seater" in str(exc_info.value).lower()

    def test_specific_time_requires_start_time(
        self, site_config, member, glider, future_date
    ):
        """Test that specific time preference requires start_time."""
        reservation = GliderReservation(
            member=member,
            glider=glider,
            date=future_date,
            reservation_type="solo",
            time_preference="specific",
            start_time=None,
        )

        with pytest.raises(ValidationError) as exc_info:
            reservation.clean()
        assert "start time" in str(exc_info.value).lower()

    def test_full_day_conflicts(self, site_config, member, glider, future_date):
        """Test full day reservation conflicts."""
        # Create a full day reservation
        GliderReservation.objects.create(
            member=member,
            glider=glider,
            date=future_date,
            reservation_type="badge",
            time_preference="full_day",
        )

        # Try to create another reservation on the same day
        reservation = GliderReservation(
            member=member,
            glider=glider,
            date=future_date,
            reservation_type="solo",
            time_preference="morning",
        )

        with pytest.raises(ValidationError) as exc_info:
            reservation.clean()
        assert "reserved for the full day" in str(exc_info.value).lower()


class TestGliderReservationForm:
    """Tests for the reservation form."""

    def test_form_valid_data(self, site_config, member, glider, future_date):
        """Test form with valid data."""
        form = GliderReservationForm(
            data={
                "glider": glider.pk,
                "date": future_date,
                "reservation_type": "solo",
                "time_preference": "morning",
            },
            member=member,
        )
        assert form.is_valid(), form.errors

    def test_form_filters_private_gliders(
        self, site_config, member, glider, private_glider, future_date
    ):
        """Test that form only shows club-owned gliders."""
        form = GliderReservationForm(member=member)
        glider_pks = [g.pk for g in form.fields["glider"].queryset]
        assert glider.pk in glider_pks
        assert private_glider.pk not in glider_pks

    def test_form_filters_two_seaters_when_disabled(
        self, site_config, member, glider, single_seat_glider, future_date
    ):
        """Test that form filters two-seaters when disabled."""
        site_config.allow_two_seater_reservations = False
        site_config.save()

        form = GliderReservationForm(member=member)
        glider_pks = [g.pk for g in form.fields["glider"].queryset]
        assert single_seat_glider.pk in glider_pks
        assert glider.pk not in glider_pks  # Two-seater should be filtered out

    def test_form_validates_past_date(self, site_config, member, glider):
        """Test form rejects past dates."""
        past_date = timezone.now().date() - timedelta(days=1)
        form = GliderReservationForm(
            data={
                "glider": glider.pk,
                "date": past_date,
                "reservation_type": "solo",
                "time_preference": "morning",
            },
            member=member,
        )
        assert not form.is_valid()
        assert "date" in form.errors


@pytest.mark.django_db
class TestGliderReservationViews:
    """Tests for reservation views."""

    def test_reservation_list_view(self, client, site_config, member):
        """Test the reservation list view."""
        client.force_login(member)
        url = reverse("duty_roster:reservation_list")
        response = client.get(url)
        assert response.status_code == 200
        assert "upcoming" in response.context
        assert "past" in response.context

    def test_reservation_create_view_get(self, client, site_config, member, glider):
        """Test the reservation create view GET."""
        client.force_login(member)
        url = reverse("duty_roster:reservation_create")
        response = client.get(url)
        assert response.status_code == 200
        assert "form" in response.context

    def test_reservation_create_view_post(
        self, client, site_config, member, glider, future_date
    ):
        """Test the reservation create view POST."""
        client.force_login(member)
        url = reverse("duty_roster:reservation_create")
        response = client.post(
            url,
            {
                "glider": glider.pk,
                "date": future_date.isoformat(),
                "reservation_type": "solo",
                "time_preference": "morning",
            },
        )
        # Should redirect on success
        assert response.status_code == 302

        # Verify reservation was created
        assert GliderReservation.objects.filter(member=member, glider=glider).exists()

    def test_reservation_detail_view(
        self, client, site_config, member, glider, future_date
    ):
        """Test the reservation detail view."""
        reservation = GliderReservation.objects.create(
            member=member,
            glider=glider,
            date=future_date,
            reservation_type="solo",
            time_preference="morning",
        )
        client.force_login(member)
        url = reverse("duty_roster:reservation_detail", args=[reservation.pk])
        response = client.get(url)
        assert response.status_code == 200
        assert response.context["reservation"] == reservation

    def test_reservation_cancel_view(
        self, client, site_config, member, glider, future_date
    ):
        """Test the reservation cancel view."""
        reservation = GliderReservation.objects.create(
            member=member,
            glider=glider,
            date=future_date,
            reservation_type="solo",
            time_preference="morning",
        )
        client.force_login(member)
        url = reverse("duty_roster:reservation_cancel", args=[reservation.pk])
        response = client.post(url, {"cancellation_reason": "Plans changed"})
        assert response.status_code == 302

        reservation.refresh_from_db()
        assert reservation.status == "cancelled"

    def test_reservation_create_disabled(self, client, site_config, member):
        """Test that reservation create redirects when disabled."""
        site_config.allow_glider_reservations = False
        site_config.save()

        client.force_login(member)
        url = reverse("duty_roster:reservation_create")
        response = client.get(url)
        # Should redirect with message
        assert response.status_code == 302

    def test_reservation_create_at_limit(
        self, client, site_config, member, glider, future_date
    ):
        """Test that reservation create redirects when at limit."""
        # Create max reservations
        for i in range(site_config.max_reservations_per_year):
            GliderReservation.objects.create(
                member=member,
                glider=glider,
                date=future_date + timedelta(days=i),
                reservation_type="solo",
                time_preference="morning",
            )

        client.force_login(member)
        url = reverse("duty_roster:reservation_create")
        response = client.get(url)
        # Should redirect with message
        assert response.status_code == 302


class TestGetReservationsForDate:
    """Tests for the get_reservations_for_date method."""

    def test_returns_confirmed_only(self, site_config, member, glider, future_date):
        """Test that only confirmed reservations are returned."""
        # Create confirmed reservation
        confirmed = GliderReservation.objects.create(
            member=member,
            glider=glider,
            date=future_date,
            reservation_type="solo",
            time_preference="morning",
            status="confirmed",
        )

        # Create cancelled reservation
        cancelled = GliderReservation.objects.create(
            member=member,
            glider=glider,
            date=future_date,
            reservation_type="solo",
            time_preference="afternoon",
            status="cancelled",
        )

        reservations = GliderReservation.get_reservations_for_date(future_date)
        assert confirmed in reservations
        assert cancelled not in reservations

    def test_returns_empty_for_no_reservations(self, site_config, future_date):
        """Test returns empty queryset when no reservations."""
        reservations = GliderReservation.get_reservations_for_date(future_date)
        assert list(reservations) == []
