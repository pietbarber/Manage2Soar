"""
Tests for validate_glider_availability() — Issue #1162.

Covers all four overlap cases in the glider-availability check:
- Case 1: both flights have launch and landing times
- Case 2: this flight is open-ended (no landing), other has a landing
- Case 3: this flight has a landing, other is open-ended (no landing)
- Case 4: both flights are open-ended (no landing)
"""

from datetime import date, time, timedelta

import pytest
from django.core.exceptions import ValidationError

from logsheet.forms import validate_glider_availability
from logsheet.models import Flight, Logsheet


def _new_flight(logsheet):
    """Create an unsaved Flight instance (pk=None) for validation."""
    return Flight(logsheet=logsheet)


class TestCase1BothHaveLanding:
    """Case 1: both flights have launch and landing times."""

    @pytest.mark.django_db
    def test_overlapping_flights_rejected(self, logsheet, glider):
        Flight.objects.create(
            logsheet=logsheet,
            glider=glider,
            launch_time=time(10, 0),
            landing_time=time(11, 0),
        )
        with pytest.raises(ValidationError):
            validate_glider_availability(
                _new_flight(logsheet),
                glider,
                launch_time=time(10, 30),
                landing_time=time(11, 30),
            )

    @pytest.mark.django_db
    def test_non_overlapping_flights_allowed(self, logsheet, glider):
        Flight.objects.create(
            logsheet=logsheet,
            glider=glider,
            launch_time=time(10, 0),
            landing_time=time(11, 0),
        )
        # Launches after the other flight has landed
        validate_glider_availability(
            _new_flight(logsheet),
            glider,
            launch_time=time(11, 0),
            landing_time=time(12, 0),
        )

    @pytest.mark.django_db
    def test_landing_exactly_when_other_launches_allowed(self, logsheet, glider):
        """Boundary: this flight lands exactly when the other launches — no overlap."""
        Flight.objects.create(
            logsheet=logsheet,
            glider=glider,
            launch_time=time(11, 0),
            landing_time=time(12, 0),
        )
        validate_glider_availability(
            _new_flight(logsheet),
            glider,
            launch_time=time(10, 0),
            landing_time=time(11, 0),
        )


class TestCase2ThisFlightOpenEnded:
    """Case 2: this flight has no landing time, other has a landing time."""

    @pytest.mark.django_db
    def test_launch_during_other_flight_rejected(self, logsheet, glider):
        Flight.objects.create(
            logsheet=logsheet,
            glider=glider,
            launch_time=time(10, 0),
            landing_time=time(11, 0),
        )
        with pytest.raises(ValidationError):
            validate_glider_availability(
                _new_flight(logsheet),
                glider,
                launch_time=time(10, 30),
                landing_time=None,
            )

    @pytest.mark.django_db
    def test_launch_before_other_flight_allowed(self, logsheet, glider):
        Flight.objects.create(
            logsheet=logsheet,
            glider=glider,
            launch_time=time(10, 0),
            landing_time=time(11, 0),
        )
        validate_glider_availability(
            _new_flight(logsheet),
            glider,
            launch_time=time(9, 0),
            landing_time=None,
        )


class TestCase3OtherFlightOpenEnded:
    """Case 3: this flight has a landing time, other has no landing time."""

    @pytest.mark.django_db
    def test_launch_at_other_launch_rejected(self, logsheet, glider):
        """FIXED: launching at the same time as an open-ended flight is a conflict."""
        Flight.objects.create(
            logsheet=logsheet,
            glider=glider,
            launch_time=time(10, 0),
        )
        with pytest.raises(ValidationError):
            validate_glider_availability(
                _new_flight(logsheet),
                glider,
                launch_time=time(10, 0),
                landing_time=time(11, 0),
            )

    @pytest.mark.django_db
    def test_launch_after_other_launch_rejected(self, logsheet, glider):
        """FIXED: launching after an open-ended flight's launch is a conflict."""
        Flight.objects.create(
            logsheet=logsheet,
            glider=glider,
            launch_time=time(10, 0),
        )
        with pytest.raises(ValidationError):
            validate_glider_availability(
                _new_flight(logsheet),
                glider,
                launch_time=time(10, 30),
                landing_time=time(11, 30),
            )

    @pytest.mark.django_db
    def test_launch_before_other_launch_allowed(self, logsheet, glider):
        """Launching before an open-ended flight's launch is allowed."""
        Flight.objects.create(
            logsheet=logsheet,
            glider=glider,
            launch_time=time(10, 0),
        )
        validate_glider_availability(
            _new_flight(logsheet),
            glider,
            launch_time=time(9, 0),
            landing_time=time(9, 30),
        )

    @pytest.mark.django_db
    def test_straddling_other_launch_rejected(self, logsheet, glider):
        """REGRESSION: this flight launched before the other's launch but lands after.

        The old condition (launch_time >= other_launch) missed this case because
        launch_time (09:00) < other_launch (10:00), even though the flight is
        still airborne at 10:00 (lands at 11:00). The corrected condition
        (landing_time > other_launch) correctly detects the overlap.
        """
        Flight.objects.create(
            logsheet=logsheet,
            glider=glider,
            launch_time=time(10, 0),
        )
        with pytest.raises(ValidationError):
            validate_glider_availability(
                _new_flight(logsheet),
                glider,
                launch_time=time(9, 0),
                landing_time=time(11, 0),
            )

    @pytest.mark.django_db
    def test_landing_at_other_launch_allowed(self, logsheet, glider):
        """BOUNDARY: landing exactly at an open-ended flight's launch is allowed.

        A flight that lands at 11:00 does not conflict with an open-ended
        flight that launches at 11:00 — the glider is on the ground by the
        time the other flight departs.
        """
        Flight.objects.create(
            logsheet=logsheet,
            glider=glider,
            launch_time=time(11, 0),
        )
        validate_glider_availability(
            _new_flight(logsheet),
            glider,
            launch_time=time(10, 0),
            landing_time=time(11, 0),
        )


class TestCase4BothOpenEnded:
    """Case 4: both flights have no landing time."""

    @pytest.mark.django_db
    def test_different_launch_times_rejected(self, logsheet, glider):
        """FIXED (primary bug): two open-ended flights at different times conflict."""
        Flight.objects.create(
            logsheet=logsheet,
            glider=glider,
            launch_time=time(10, 0),
        )
        with pytest.raises(ValidationError):
            validate_glider_availability(
                _new_flight(logsheet),
                glider,
                launch_time=time(11, 0),
                landing_time=None,
            )

    @pytest.mark.django_db
    def test_same_launch_time_rejected(self, logsheet, glider):
        Flight.objects.create(
            logsheet=logsheet,
            glider=glider,
            launch_time=time(10, 0),
        )
        with pytest.raises(ValidationError):
            validate_glider_availability(
                _new_flight(logsheet),
                glider,
                launch_time=time(10, 0),
                landing_time=None,
            )


class TestEdgeCases:
    """Edge cases and early-return paths."""

    @pytest.mark.django_db
    def test_different_dates_no_conflict(self, logsheet, glider):
        other_logsheet = Logsheet.objects.create(
            log_date=date.today() - timedelta(days=1),
            airfield=logsheet.airfield,
            created_by=logsheet.created_by,
        )
        Flight.objects.create(
            logsheet=other_logsheet,
            glider=glider,
            launch_time=time(10, 0),
        )
        validate_glider_availability(
            _new_flight(logsheet),
            glider,
            launch_time=time(10, 0),
            landing_time=None,
        )

    @pytest.mark.django_db
    def test_editing_existing_flight_excludes_self(self, logsheet, glider):
        """A flight being edited should not conflict with itself."""
        existing = Flight.objects.create(
            logsheet=logsheet,
            glider=glider,
            launch_time=time(10, 0),
            landing_time=time(11, 0),
        )
        # Re-validating the same flight's times should not raise
        validate_glider_availability(
            existing,
            glider,
            launch_time=time(10, 0),
            landing_time=time(11, 0),
        )

    @pytest.mark.django_db
    def test_no_glider_skips_validation(self, logsheet):
        validate_glider_availability(
            _new_flight(logsheet),
            None,
            launch_time=time(10, 0),
            landing_time=time(11, 0),
        )

    @pytest.mark.django_db
    def test_no_launch_time_skips_validation(self, logsheet, glider):
        validate_glider_availability(
            _new_flight(logsheet),
            glider,
            launch_time=None,
            landing_time=time(11, 0),
        )

    @pytest.mark.django_db
    def test_other_flight_without_launch_time_skipped(self, logsheet, glider):
        Flight.objects.create(logsheet=logsheet, glider=glider)
        validate_glider_availability(
            _new_flight(logsheet),
            glider,
            launch_time=time(10, 0),
            landing_time=time(11, 0),
        )

    @pytest.mark.django_db
    def test_flight_without_logsheet_skips_validation(self, glider):
        validate_glider_availability(
            Flight(),
            glider,
            launch_time=time(10, 0),
            landing_time=time(11, 0),
        )
