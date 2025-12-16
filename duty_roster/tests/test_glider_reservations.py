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

from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from duty_roster.forms import GliderReservationForm
from duty_roster.models import GliderReservation
from logsheet.models import Glider, MaintenanceIssue
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
        GliderReservation.objects.create(
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

    def test_monthly_count(self, site_config, member, glider, future_date):
        """Test getting monthly reservation count for a member."""
        # Create some reservations in the current month
        for i in range(2):
            GliderReservation.objects.create(
                member=member,
                glider=glider,
                date=future_date + timedelta(days=i),
                reservation_type="solo",
                time_preference="morning",
            )

        count = GliderReservation.get_member_monthly_count(
            member, future_date.year, future_date.month
        )
        assert count == 2

    def test_can_member_reserve_with_monthly_limit(
        self, site_config, member, glider, future_date
    ):
        """Test monthly reservation limit enforcement."""
        site_config.max_reservations_per_month = 2
        site_config.max_reservations_per_year = 0  # Unlimited yearly
        site_config.save()

        # Create reservations up to the monthly limit
        for i in range(2):
            GliderReservation.objects.create(
                member=member,
                glider=glider,
                date=future_date + timedelta(days=i),
                reservation_type="solo",
                time_preference="morning",
            )

        # Now at monthly limit
        can_reserve, message = GliderReservation.can_member_reserve(
            member, future_date.year, future_date.month
        )
        assert can_reserve is False
        assert "month" in message.lower()

    def test_monthly_limit_unlimited(self, site_config, member, glider, future_date):
        """Test unlimited monthly reservations when max_per_month is 0."""
        site_config.max_reservations_per_month = 0  # Unlimited monthly
        site_config.max_reservations_per_year = 0  # Unlimited yearly
        site_config.save()

        # Create many reservations in same month
        for i in range(5):
            GliderReservation.objects.create(
                member=member,
                glider=glider,
                date=future_date + timedelta(days=i),
                reservation_type="solo",
                time_preference="morning",
            )

        # Can still reserve
        can_reserve, message = GliderReservation.can_member_reserve(
            member, future_date.year, future_date.month
        )
        assert can_reserve is True

    def test_both_yearly_and_monthly_limits(
        self, site_config, member, glider, future_date
    ):
        """Test that both yearly and monthly limits are enforced."""
        site_config.max_reservations_per_month = 2
        site_config.max_reservations_per_year = 10
        site_config.save()

        # Create 2 reservations this month (at monthly limit)
        for i in range(2):
            GliderReservation.objects.create(
                member=member,
                glider=glider,
                date=future_date + timedelta(days=i),
                reservation_type="solo",
                time_preference="morning",
            )

        # Should be blocked by monthly limit even though yearly limit not reached
        can_reserve, message = GliderReservation.can_member_reserve(
            member, future_date.year, future_date.month
        )
        assert can_reserve is False
        assert "month" in message.lower()

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

    def test_reservation_form_blocks_monthly_limit(
        self, site_config, member, glider, future_date
    ):
        """Test that form validation blocks reservations at monthly limit."""
        site_config.max_reservations_per_month = 1
        site_config.max_reservations_per_year = 10
        site_config.save()

        # Use a date in the future that's within the same month as future_date
        first_date = future_date
        second_date = future_date + timedelta(days=1)

        # Ensure both dates are in the same month (for test validity)
        if second_date.month != first_date.month:
            # Adjust if dates span months
            second_date = first_date

        # Create 1 reservation in the test month
        GliderReservation.objects.create(
            member=member,
            glider=glider,
            date=first_date,
            reservation_type="solo",
            time_preference="morning",
        )

        # Try to create another reservation in the same month via form
        form = GliderReservationForm(
            data={
                "glider": glider.pk,
                "date": second_date,
                "reservation_type": "solo",
                "time_preference": "afternoon",
            },
            member=member,
        )

        # Form should be invalid due to monthly limit
        assert form.is_valid() is False
        # Check that error message mentions month
        errors_str = str(form.errors)
        assert "month" in errors_str.lower() or "maximum" in errors_str.lower()


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


class TestConcurrentReservations:
    """Tests for concurrent reservation creation and race condition handling."""

    def test_duplicate_reservation_raises_integrity_error(
        self, site_config, member, glider, future_date
    ):
        """Test that creating duplicate reservations raises IntegrityError."""
        from django.db import IntegrityError

        # Create first reservation
        GliderReservation.objects.create(
            member=member,
            glider=glider,
            date=future_date,
            reservation_type="solo",
            time_preference="morning",
            status="confirmed",
        )

        # Try to create duplicate (same glider, date, time_preference, status)
        with pytest.raises(IntegrityError):
            GliderReservation.objects.create(
                member=member,
                glider=glider,
                date=future_date,
                reservation_type="solo",
                time_preference="morning",
                status="confirmed",
            )

    def test_form_handles_integrity_error(
        self, site_config, member, glider, single_seat_glider, future_date
    ):
        """Test that form gracefully handles IntegrityError during save."""
        from unittest.mock import patch

        from django.db import IntegrityError

        # Create form with valid data
        form = GliderReservationForm(
            data={
                "glider": single_seat_glider.pk,
                "date": future_date,
                "reservation_type": "solo",
                "time_preference": "morning",
            },
            member=member,
        )

        # Form should validate successfully
        assert form.is_valid()

        # Mock save() to raise IntegrityError (simulating race condition)
        original_save = GliderReservation.save

        def mock_save(self, *args, **kwargs):
            if not self.pk:  # Only raise on first save
                raise IntegrityError("unique constraint violated")
            return original_save(self, *args, **kwargs)

        with patch.object(GliderReservation, "save", mock_save):
            # Save should not raise exception, but should add error to form
            form.save()

            # Form should have non-field error about unavailability
            assert "no longer available" in str(form.non_field_errors()).lower()

    def test_view_rerenders_form_on_integrity_error(
        self, client, site_config, member, glider, single_seat_glider, future_date
    ):
        """Test that view re-renders form (doesn't redirect) when save fails."""
        from unittest.mock import patch

        from django.db import IntegrityError

        client.force_login(member)
        url = reverse("duty_roster:reservation_create")

        # Mock GliderReservation.save to raise IntegrityError
        original_save = GliderReservation.save

        def mock_save(self, *args, **kwargs):
            if not self.pk:  # Only raise on first save
                raise IntegrityError("unique constraint violated")
            return original_save(self, *args, **kwargs)

        with patch.object(GliderReservation, "save", mock_save):
            response = client.post(
                url,
                {
                    "glider": single_seat_glider.pk,
                    "date": future_date.isoformat(),
                    "reservation_type": "solo",
                    "time_preference": "morning",
                },
            )

            # Should re-render form (200) not redirect (302)
            assert response.status_code == 200

            # Form should be in context
            assert "form" in response.context

            # Form should have errors
            form = response.context["form"]
            assert len(form.non_field_errors()) > 0

    def test_concurrent_yearly_limit_race_condition(
        self, site_config, member, glider, future_date
    ):
        """Test that yearly limit check uses database locking to prevent race conditions."""
        from django.db import transaction

        # Create reservations up to one below the limit (use different days to avoid conflicts)
        for i in range(site_config.max_reservations_per_year - 1):
            GliderReservation.objects.create(
                member=member,
                glider=glider,
                date=future_date + timedelta(days=i * 2),  # Space them out
                reservation_type="solo",
                time_preference="morning",
            )

        # Verify member can still make one more reservation
        count_before = GliderReservation.get_member_yearly_count(member)
        assert count_before == site_config.max_reservations_per_year - 1

        # Create and validate a form (use a different day in the same year)
        form = GliderReservationForm(
            data={
                "glider": glider.pk,
                "date": (
                    future_date + timedelta(days=5)
                ).isoformat(),  # Stay in same year
                "reservation_type": "solo",
                "time_preference": "afternoon",  # Different time to avoid any conflicts
            },
            member=member,
        )

        # Form should validate (member has one spot left)
        assert form.is_valid(), f"Form errors: {form.errors}"

        # Save should succeed
        reservation = form.save()
        assert (
            reservation.pk is not None
        ), f"Reservation not saved. Form errors: {form.errors}"

        # Check if reservation actually exists in database
        db_reservation = GliderReservation.objects.filter(pk=reservation.pk).first()
        assert (
            db_reservation is not None
        ), f"Reservation {reservation.pk} not found in database"

        # Verify member is now at limit
        count_after = GliderReservation.get_member_yearly_count(member)
        all_reservations = list(
            GliderReservation.objects.filter(
                member=member, status__in=["confirmed", "completed"]
            ).values_list("date", "time_preference", "status")
        )
        assert (
            count_after == site_config.max_reservations_per_year
        ), f"Expected {site_config.max_reservations_per_year}, got {count_after}. All reservations: {all_reservations}. Form errors: {form.errors}"

        # Try to create another reservation - should fail validation
        form2 = GliderReservationForm(
            data={
                "glider": glider.pk,
                "date": (future_date + timedelta(days=6)).isoformat(),  # Same year
                "reservation_type": "solo",
                "time_preference": "midday",
            },
            member=member,
        )

        # This form should fail validation due to limit
        assert not form2.is_valid()
        error_text = str(form2.non_field_errors()).lower()
        assert (
            "reached" in error_text or "limit" in error_text or "maximum" in error_text
        )

    def test_cancelled_reservations_dont_count_toward_limit(
        self, site_config, member, glider, future_date
    ):
        """Test that cancelled reservations don't count toward yearly limit."""
        # Create and cancel max reservations
        for i in range(site_config.max_reservations_per_year):
            res = GliderReservation.objects.create(
                member=member,
                glider=glider,
                date=future_date + timedelta(days=i),
                reservation_type="solo",
                time_preference="morning",
            )
            res.cancel(reason="Testing")

        # Should still be able to create new reservation
        can_reserve, message = GliderReservation.can_member_reserve(member)
        assert can_reserve is True

        # Create new reservation should succeed
        form = GliderReservationForm(
            data={
                "glider": glider.pk,
                "date": future_date + timedelta(days=20),
                "reservation_type": "solo",
                "time_preference": "morning",
            },
            member=member,
        )
        assert form.is_valid()
        reservation = form.save()
        assert reservation.pk is not None


class TestMarkCompletedAndNoShow:
    """Tests for mark_completed() and mark_no_show() methods."""

    def test_mark_completed(self, site_config, member, glider, future_date):
        """Test marking a reservation as completed."""
        reservation = GliderReservation.objects.create(
            member=member,
            glider=glider,
            date=future_date,
            reservation_type="solo",
            time_preference="morning",
        )
        assert reservation.status == "confirmed"

        reservation.mark_completed()
        reservation.refresh_from_db()

        assert reservation.status == "completed"

    def test_mark_no_show(self, site_config, member, glider, future_date):
        """Test marking a reservation as no-show."""
        reservation = GliderReservation.objects.create(
            member=member,
            glider=glider,
            date=future_date,
            reservation_type="solo",
            time_preference="morning",
        )
        assert reservation.status == "confirmed"

        reservation.mark_no_show()
        reservation.refresh_from_db()

        assert reservation.status == "no_show"

    def test_completed_counts_toward_yearly_limit(
        self, site_config, member, glider, future_date
    ):
        """Test that completed reservations count toward yearly limit."""
        # Create and mark as completed
        for i in range(site_config.max_reservations_per_year):
            res = GliderReservation.objects.create(
                member=member,
                glider=glider,
                date=future_date + timedelta(days=i),
                reservation_type="solo",
                time_preference="morning",
            )
            res.mark_completed()

        # Should be at limit
        can_reserve, message = GliderReservation.can_member_reserve(member)
        assert can_reserve is False
        assert "limit" in message.lower()

    def test_no_show_does_not_count_toward_limit(
        self, site_config, member, glider, future_date
    ):
        """Test that no-show reservations don't count toward yearly limit."""
        # Create and mark as no-show
        for i in range(site_config.max_reservations_per_year):
            res = GliderReservation.objects.create(
                member=member,
                glider=glider,
                date=future_date + timedelta(days=i),
                reservation_type="solo",
                time_preference="morning",
            )
            res.mark_no_show()

        # Should still be able to reserve (no-shows don't count)
        can_reserve, message = GliderReservation.can_member_reserve(member)
        assert can_reserve is True


class TestTimePreferenceConflicts:
    """Tests for time preference conflict detection."""

    def test_same_time_preference_conflicts(
        self, site_config, member, glider, future_date
    ):
        """Test that reservations with same time preference conflict."""
        # Create morning reservation
        GliderReservation.objects.create(
            member=member,
            glider=glider,
            date=future_date,
            reservation_type="solo",
            time_preference="morning",
        )

        # Try to create another morning reservation
        reservation = GliderReservation(
            member=member,
            glider=glider,
            date=future_date,
            reservation_type="solo",
            time_preference="morning",
        )

        with pytest.raises(ValidationError) as exc_info:
            reservation.clean()
        assert "already reserved" in str(exc_info.value).lower()

    def test_different_time_preferences_allowed(
        self, site_config, member, glider, single_seat_glider, future_date
    ):
        """Test that different time preferences on same day are allowed."""
        # Create morning reservation
        GliderReservation.objects.create(
            member=member,
            glider=glider,
            date=future_date,
            reservation_type="solo",
            time_preference="morning",
        )

        # Afternoon reservation should be allowed
        afternoon_res = GliderReservation(
            member=member,
            glider=glider,
            date=future_date,
            reservation_type="solo",
            time_preference="afternoon",
        )

        # Should not raise ValidationError
        afternoon_res.clean()
        afternoon_res.save()
        assert afternoon_res.pk is not None
