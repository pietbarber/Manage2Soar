"""Tests for the MailingList model and API integration."""

import pytest
from django.core.exceptions import ValidationError

from logsheet.models import Glider
from members.models import Member
from siteconfig.models import MailingList, MailingListCriterion, MembershipStatus


@pytest.fixture
def membership_status(db):
    """Create an active membership status for testing."""
    status, _ = MembershipStatus.objects.get_or_create(
        name="Full Member", defaults={"is_active": True, "sort_order": 10}
    )
    return status


@pytest.fixture
def inactive_status(db):
    """Create an inactive membership status for testing."""
    status, _ = MembershipStatus.objects.get_or_create(
        name="Inactive Member", defaults={"is_active": False, "sort_order": 100}
    )
    return status


@pytest.fixture
def active_member(membership_status):
    """Create an active member for testing."""
    return Member.objects.create(
        username="active_member",
        email="active@example.com",
        first_name="Active",
        last_name="Member",
        membership_status="Full Member",
        is_active=True,
    )


@pytest.fixture
def inactive_member(inactive_status):
    """Create an inactive member for testing."""
    return Member.objects.create(
        username="inactive_member",
        email="inactive@example.com",
        first_name="Inactive",
        last_name="Member",
        membership_status="Inactive Member",
        is_active=True,
    )


@pytest.fixture
def instructor_member(membership_status):
    """Create an instructor member for testing."""
    return Member.objects.create(
        username="instructor",
        email="instructor@example.com",
        first_name="Instructor",
        last_name="Member",
        membership_status="Full Member",
        is_active=True,
        instructor=True,
    )


@pytest.fixture
def towpilot_member(membership_status):
    """Create a tow pilot member for testing."""
    return Member.objects.create(
        username="towpilot",
        email="towpilot@example.com",
        first_name="Tow",
        last_name="Pilot",
        membership_status="Full Member",
        is_active=True,
        towpilot=True,
    )


@pytest.fixture
def duty_officer_member(membership_status):
    """Create a duty officer member for testing."""
    return Member.objects.create(
        username="do",
        email="do@example.com",
        first_name="Duty",
        last_name="Officer",
        membership_status="Full Member",
        is_active=True,
        duty_officer=True,
    )


@pytest.fixture
def director_member(membership_status):
    """Create a director member for testing."""
    return Member.objects.create(
        username="director",
        email="director@example.com",
        first_name="Board",
        last_name="Director",
        membership_status="Full Member",
        is_active=True,
        director=True,
    )


@pytest.fixture
def private_glider_owner(membership_status):
    """Create a private glider owner for testing."""
    member = Member.objects.create(
        username="glider_owner",
        email="owner@example.com",
        first_name="Glider",
        last_name="Owner",
        membership_status="Full Member",
        is_active=True,
    )
    # Create a private glider and assign this member as owner
    glider = Glider.objects.create(
        n_number="N12345",
        competition_number="AB",
        model="ASW-20",
        club_owned=False,  # Private glider
        is_active=True,
    )
    glider.owners.add(member)
    return member


@pytest.mark.django_db
class TestMailingListModel:
    """Tests for the MailingList model."""

    def test_create_mailing_list(self):
        """Test creating a basic mailing list."""
        ml = MailingList.objects.create(
            name="members",
            email_address="members@example.com",
            description="All active members",
            is_active=True,
            criteria=[MailingListCriterion.ACTIVE_MEMBER],
        )
        assert ml.name == "members"
        assert ml.is_active is True
        assert MailingListCriterion.ACTIVE_MEMBER in ml.criteria

    def test_unique_name_constraint(self):
        """Test that mailing list names must be unique."""
        MailingList.objects.create(
            name="test-list",
            criteria=[MailingListCriterion.ACTIVE_MEMBER],
        )
        with pytest.raises(Exception):
            MailingList.objects.create(
                name="test-list",
                criteria=[MailingListCriterion.INSTRUCTOR],
            )

    def test_criteria_validation_valid(self):
        """Test that valid criteria pass validation."""
        ml = MailingList(
            name="valid-list",
            criteria=[MailingListCriterion.INSTRUCTOR, MailingListCriterion.TOWPILOT],
        )
        ml.full_clean()  # Should not raise

    def test_criteria_validation_invalid(self):
        """Test that invalid criteria codes fail validation."""
        ml = MailingList(
            name="invalid-list",
            criteria=["invalid_criterion", "another_invalid"],
        )
        with pytest.raises(ValidationError) as exc_info:
            ml.full_clean()
        assert "Invalid criteria codes" in str(exc_info.value)

    def test_criteria_display(self):
        """Test the get_criteria_display method."""
        ml = MailingList.objects.create(
            name="display-test",
            criteria=[MailingListCriterion.INSTRUCTOR, MailingListCriterion.DIRECTOR],
        )
        display = ml.get_criteria_display()
        assert "Instructor" in display
        assert "Director" in display

    def test_empty_criteria_display(self):
        """Test get_criteria_display with no criteria."""
        ml = MailingList.objects.create(name="empty-list", criteria=[])
        assert ml.get_criteria_display() == []

    def test_str_representation(self):
        """Test string representation of MailingList."""
        ml = MailingList.objects.create(name="str-test", criteria=[])
        assert str(ml) == "str-test"


@pytest.mark.django_db
class TestMailingListSubscribers:
    """Tests for subscriber queries."""

    def test_active_member_criterion(self, active_member, inactive_member):
        """Test ACTIVE_MEMBER criterion includes only active members."""
        ml = MailingList.objects.create(
            name="members",
            criteria=[MailingListCriterion.ACTIVE_MEMBER],
        )
        subscribers = ml.get_subscribers()
        assert active_member in subscribers
        assert inactive_member not in subscribers

    def test_instructor_criterion(self, active_member, instructor_member):
        """Test INSTRUCTOR criterion includes only instructors."""
        ml = MailingList.objects.create(
            name="instructors",
            criteria=[MailingListCriterion.INSTRUCTOR],
        )
        subscribers = ml.get_subscribers()
        assert instructor_member in subscribers
        assert active_member not in subscribers

    def test_towpilot_criterion(self, active_member, towpilot_member):
        """Test TOWPILOT criterion includes only tow pilots."""
        ml = MailingList.objects.create(
            name="towpilots",
            criteria=[MailingListCriterion.TOWPILOT],
        )
        subscribers = ml.get_subscribers()
        assert towpilot_member in subscribers
        assert active_member not in subscribers

    def test_duty_officer_criterion(self, active_member, duty_officer_member):
        """Test DUTY_OFFICER criterion includes only duty officers."""
        ml = MailingList.objects.create(
            name="duty-officers",
            criteria=[MailingListCriterion.DUTY_OFFICER],
        )
        subscribers = ml.get_subscribers()
        assert duty_officer_member in subscribers
        assert active_member not in subscribers

    def test_director_criterion(self, active_member, director_member):
        """Test DIRECTOR criterion includes only directors."""
        ml = MailingList.objects.create(
            name="directors",
            criteria=[MailingListCriterion.DIRECTOR],
        )
        subscribers = ml.get_subscribers()
        assert director_member in subscribers
        assert active_member not in subscribers

    def test_private_glider_owner_criterion(self, active_member, private_glider_owner):
        """Test PRIVATE_GLIDER_OWNER criterion includes only private glider owners."""
        ml = MailingList.objects.create(
            name="private-owners",
            criteria=[MailingListCriterion.PRIVATE_GLIDER_OWNER],
        )
        subscribers = ml.get_subscribers()
        assert private_glider_owner in subscribers
        assert active_member not in subscribers

    def test_multiple_criteria_or_logic(
        self, active_member, instructor_member, towpilot_member
    ):
        """Test that multiple criteria use OR logic."""
        ml = MailingList.objects.create(
            name="operations",
            criteria=[MailingListCriterion.INSTRUCTOR, MailingListCriterion.TOWPILOT],
        )
        subscribers = ml.get_subscribers()
        # Both instructor and towpilot should be included (OR logic)
        assert instructor_member in subscribers
        assert towpilot_member in subscribers
        # Regular member should not be included
        assert active_member not in subscribers

    def test_get_subscriber_emails(self, instructor_member):
        """Test get_subscriber_emails returns email list."""
        ml = MailingList.objects.create(
            name="email-test",
            criteria=[MailingListCriterion.INSTRUCTOR],
        )
        emails = ml.get_subscriber_emails()
        assert "instructor@example.com" in emails

    def test_get_subscriber_count(self, instructor_member, towpilot_member):
        """Test get_subscriber_count returns correct count."""
        ml = MailingList.objects.create(
            name="count-test",
            criteria=[MailingListCriterion.INSTRUCTOR, MailingListCriterion.TOWPILOT],
        )
        assert ml.get_subscriber_count() == 2

    def test_empty_criteria_returns_none(self, active_member):
        """Test that empty criteria returns no subscribers."""
        ml = MailingList.objects.create(name="empty-list", criteria=[])
        assert ml.get_subscriber_count() == 0

    def test_member_without_email_excluded(self, membership_status):
        """Test that members without email are excluded from subscriber lists and counts."""
        Member.objects.create(
            username="no_email",
            email="",  # No email
            first_name="No",
            last_name="Email",
            membership_status="Full Member",
            is_active=True,
            instructor=True,
        )
        ml = MailingList.objects.create(
            name="instructors",
            criteria=[MailingListCriterion.INSTRUCTOR],
        )
        emails = ml.get_subscriber_emails()
        assert "" not in emails
        # Verify count also excludes members without valid emails
        assert ml.get_subscriber_count() == 0


@pytest.mark.django_db
class TestMailingListOrdering:
    """Tests for mailing list ordering."""

    def test_ordering_by_sort_order_then_name(self):
        """Test that mailing lists are ordered by sort_order then name."""
        ml_c = MailingList.objects.create(name="charlie", sort_order=30, criteria=[])
        ml_a = MailingList.objects.create(name="alpha", sort_order=10, criteria=[])
        ml_b = MailingList.objects.create(name="bravo", sort_order=20, criteria=[])

        lists = list(MailingList.objects.all())
        assert lists[0] == ml_a
        assert lists[1] == ml_b
        assert lists[2] == ml_c

    def test_same_sort_order_ordered_by_name(self):
        """Test that lists with same sort_order are ordered by name."""
        ml_z = MailingList.objects.create(name="zulu", sort_order=10, criteria=[])
        ml_a = MailingList.objects.create(name="alpha", sort_order=10, criteria=[])

        lists = list(MailingList.objects.all())
        assert lists[0] == ml_a
        assert lists[1] == ml_z
