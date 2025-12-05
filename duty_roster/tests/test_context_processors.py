"""
Tests for duty_roster context processors.
"""

from datetime import date, timedelta
from unittest.mock import MagicMock

import pytest
from django.core.cache import cache
from django.test import RequestFactory

from duty_roster.context_processors import (
    instructor_pending_requests,
    invalidate_instructor_pending_cache,
)
from duty_roster.models import DutyAssignment, InstructionSlot
from members.models import Member
from siteconfig.models import MembershipStatus


@pytest.fixture
def membership_statuses(db):
    """Create required membership statuses for testing."""
    MembershipStatus.objects.get_or_create(
        name="Full Member", defaults={"is_active": True, "sort_order": 1}
    )


@pytest.fixture
def request_factory():
    """Provide a request factory."""
    return RequestFactory()


@pytest.fixture
def regular_user(db, membership_statuses):
    """Create a regular (non-instructor) user."""
    user = Member.objects.create_user(
        username="regularuser",
        email="regular@example.com",
        password="testpass123",
        first_name="Regular",
        last_name="User",
        membership_status="Full Member",
    )
    return user


@pytest.fixture
def instructor_user(db, membership_statuses):
    """Create an instructor user."""
    user = Member.objects.create_user(
        username="testinstructor",
        email="instructor@example.com",
        password="testpass123",
        first_name="Test",
        last_name="Instructor",
        membership_status="Full Member",
        instructor=True,
    )
    return user


@pytest.fixture
def surge_instructor_user(db, membership_statuses):
    """Create a second instructor for surge testing."""
    user = Member.objects.create_user(
        username="surgeinstructor",
        email="surge@example.com",
        password="testpass123",
        first_name="Surge",
        last_name="Instructor",
        membership_status="Full Member",
        instructor=True,
    )
    return user


@pytest.fixture
def student_user(db, membership_statuses):
    """Create a student user."""
    return Member.objects.create_user(
        username="teststudent",
        email="student@example.com",
        password="testpass123",
        first_name="Test",
        last_name="Student",
        membership_status="Full Member",
    )


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear cache before and after each test."""
    cache.clear()
    yield
    cache.clear()


class TestInstructorPendingRequests:
    """Tests for instructor_pending_requests context processor."""

    def test_unauthenticated_user_returns_zero(self, request_factory):
        """Unauthenticated users should get pending_count of 0."""
        request = request_factory.get("/")
        request.user = MagicMock()
        request.user.is_authenticated = False

        result = instructor_pending_requests(request)

        assert result == {"instructor_pending_count": 0}

    def test_non_instructor_returns_zero(self, request_factory, regular_user):
        """Non-instructor authenticated users should get pending_count of 0."""
        request = request_factory.get("/")
        request.user = regular_user

        result = instructor_pending_requests(request)

        assert result == {"instructor_pending_count": 0}

    def test_instructor_with_no_pending_returns_zero(
        self, request_factory, instructor_user
    ):
        """Instructor with no pending requests should get 0."""
        request = request_factory.get("/")
        request.user = instructor_user

        result = instructor_pending_requests(request)

        assert result == {"instructor_pending_count": 0}

    def test_instructor_with_pending_requests(
        self, request_factory, instructor_user, student_user
    ):
        """Instructor with pending requests should get correct count."""
        request = request_factory.get("/")
        request.user = instructor_user

        # Create a future duty assignment with this instructor
        future_date = date.today() + timedelta(days=7)
        assignment = DutyAssignment.objects.create(
            date=future_date,
            instructor=instructor_user,
        )

        # Create pending instruction slots
        InstructionSlot.objects.create(
            assignment=assignment,
            student=student_user,
            status="pending",
            instructor_response="pending",
        )

        result = instructor_pending_requests(request)

        assert result == {"instructor_pending_count": 1}

    def test_excludes_past_dates(self, request_factory, instructor_user, student_user):
        """Should not count requests for past dates."""
        request = request_factory.get("/")
        request.user = instructor_user

        # Create a past duty assignment
        past_date = date.today() - timedelta(days=1)
        assignment = DutyAssignment.objects.create(
            date=past_date,
            instructor=instructor_user,
        )

        # Create pending instruction slot for past date
        InstructionSlot.objects.create(
            assignment=assignment,
            student=student_user,
            status="pending",
            instructor_response="pending",
        )

        result = instructor_pending_requests(request)

        assert result == {"instructor_pending_count": 0}

    def test_excludes_cancelled_requests(
        self, request_factory, instructor_user, student_user
    ):
        """Should not count cancelled requests."""
        request = request_factory.get("/")
        request.user = instructor_user

        # Create a future duty assignment
        future_date = date.today() + timedelta(days=7)
        assignment = DutyAssignment.objects.create(
            date=future_date,
            instructor=instructor_user,
        )

        # Create cancelled instruction slot
        InstructionSlot.objects.create(
            assignment=assignment,
            student=student_user,
            status="cancelled",
            instructor_response="pending",
        )

        result = instructor_pending_requests(request)

        assert result == {"instructor_pending_count": 0}

    def test_surge_instructor_sees_pending(
        self, request_factory, instructor_user, surge_instructor_user, student_user
    ):
        """Surge instructor should also see pending requests."""
        request = request_factory.get("/")
        request.user = surge_instructor_user

        # Create assignment with primary and surge instructor
        future_date = date.today() + timedelta(days=7)
        assignment = DutyAssignment.objects.create(
            date=future_date,
            instructor=instructor_user,
            surge_instructor=surge_instructor_user,
        )

        # Create pending instruction slot
        InstructionSlot.objects.create(
            assignment=assignment,
            student=student_user,
            status="pending",
            instructor_response="pending",
        )

        result = instructor_pending_requests(request)

        assert result == {"instructor_pending_count": 1}


class TestCaching:
    """Tests for caching behavior."""

    def test_cache_is_used_without_changes(
        self, request_factory, instructor_user, student_user
    ):
        """Repeated requests without data changes should use cached value."""
        request = request_factory.get("/")
        request.user = instructor_user

        # Create a pending request
        future_date = date.today() + timedelta(days=7)
        assignment = DutyAssignment.objects.create(
            date=future_date,
            instructor=instructor_user,
        )
        InstructionSlot.objects.create(
            assignment=assignment,
            student=student_user,
            status="pending",
            instructor_response="pending",
        )

        # First call - should hit DB and cache result
        result1 = instructor_pending_requests(request)
        assert result1 == {"instructor_pending_count": 1}

        # Second call - should use cached value (no data changed)
        result2 = instructor_pending_requests(request)
        assert result2 == {"instructor_pending_count": 1}

        # Third call - still cached
        result3 = instructor_pending_requests(request)
        assert result3 == {"instructor_pending_count": 1}

    def test_cache_invalidated_on_new_slot(
        self, request_factory, instructor_user, student_user, membership_statuses
    ):
        """Cache should be invalidated when a new InstructionSlot is created."""
        request = request_factory.get("/")
        request.user = instructor_user

        # Create a pending request
        future_date = date.today() + timedelta(days=7)
        assignment = DutyAssignment.objects.create(
            date=future_date,
            instructor=instructor_user,
        )
        InstructionSlot.objects.create(
            assignment=assignment,
            student=student_user,
            status="pending",
            instructor_response="pending",
        )

        # First call - should hit DB
        result1 = instructor_pending_requests(request)
        assert result1 == {"instructor_pending_count": 1}

        # Create another pending request (signal should invalidate cache)
        student2 = Member.objects.create_user(
            username="student2",
            email="student2@example.com",
            password="testpass123",
            first_name="Student",
            last_name="Two",
            membership_status="Full Member",
        )
        InstructionSlot.objects.create(
            assignment=assignment,
            student=student2,
            status="pending",
            instructor_response="pending",
        )

        # Second call - should return fresh count (cache was invalidated by signal)
        result2 = instructor_pending_requests(request)
        assert result2 == {"instructor_pending_count": 2}

    def test_invalidate_cache(self, instructor_user):
        """Cache invalidation should work."""
        cache_key = f"instructor_pending_count_{instructor_user.id}"

        # Set a value in cache
        cache.set(cache_key, 5, 300)
        assert cache.get(cache_key) == 5

        # Invalidate
        invalidate_instructor_pending_cache(instructor_user.id)

        # Should be None now
        assert cache.get(cache_key) is None

    def test_cache_invalidation_after_new_request(
        self, request_factory, instructor_user, student_user
    ):
        """Cache should be invalidated when InstructionSlot is created."""
        request = request_factory.get("/")
        request.user = instructor_user

        # First call - should be 0
        result1 = instructor_pending_requests(request)
        assert result1 == {"instructor_pending_count": 0}

        # Create a pending request
        future_date = date.today() + timedelta(days=7)
        assignment = DutyAssignment.objects.create(
            date=future_date,
            instructor=instructor_user,
        )

        # Manually invalidate cache (signals do this automatically)
        invalidate_instructor_pending_cache(instructor_user.id)

        # Create slot
        InstructionSlot.objects.create(
            assignment=assignment,
            student=student_user,
            status="pending",
            instructor_response="pending",
        )

        # After invalidation, should get fresh count
        result2 = instructor_pending_requests(request)
        assert result2 == {"instructor_pending_count": 1}

    def test_cache_invalidation_on_slot_delete(
        self, request_factory, instructor_user, student_user
    ):
        """Cache should be invalidated when InstructionSlot is deleted."""
        request = request_factory.get("/")
        request.user = instructor_user

        # Create a pending request
        future_date = date.today() + timedelta(days=7)
        assignment = DutyAssignment.objects.create(
            date=future_date,
            instructor=instructor_user,
        )

        slot = InstructionSlot.objects.create(
            assignment=assignment,
            student=student_user,
            status="pending",
            instructor_response="pending",
        )

        # First call - should be 1
        result1 = instructor_pending_requests(request)
        assert result1 == {"instructor_pending_count": 1}

        # Delete the slot (signal should invalidate cache)
        slot.delete()

        # After deletion, should get fresh count of 0
        result2 = instructor_pending_requests(request)
        assert result2 == {"instructor_pending_count": 0}
