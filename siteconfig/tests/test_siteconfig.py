import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from siteconfig.models import MembershipStatus, SiteConfiguration

User = get_user_model()


@pytest.mark.django_db
def test_create_siteconfiguration():
    SiteConfiguration.objects.create(
        club_name="Skyline Soaring", domain_name="example.org", club_abbreviation="SSS"
    )
    assert SiteConfiguration.objects.filter(club_name="Skyline Soaring").exists()


@pytest.mark.django_db
def test_update_siteconfiguration():
    c = SiteConfiguration.objects.create(
        club_name="Old Name", domain_name="example.org", club_abbreviation="SSS"
    )
    c.club_name = "New Name"
    c.save()
    c.refresh_from_db()
    assert c.club_name == "New Name"


# MembershipStatus Tests
@pytest.mark.django_db
def test_create_membership_status():
    """Test creating a basic membership status."""
    status = MembershipStatus.objects.create(
        name="Test Member",
        is_active=True,
        sort_order=100,
        description="A test membership status",
    )
    assert status.name == "Test Member"
    assert status.is_active is True
    assert status.sort_order == 100
    assert status.description == "A test membership status"


@pytest.mark.django_db
def test_membership_status_unique_name():
    """Test that membership status names must be unique."""
    MembershipStatus.objects.create(name="Unique Test Member", is_active=True)

    with pytest.raises(
        Exception
    ):  # Should raise IntegrityError due to unique constraint
        MembershipStatus.objects.create(name="Unique Test Member", is_active=False)


@pytest.mark.django_db
def test_membership_status_str():
    """Test the string representation of MembershipStatus."""
    status = MembershipStatus.objects.create(name="Test String Member", is_active=True)
    assert str(status) == "Test String Member"


@pytest.mark.django_db(transaction=True)
def test_membership_status_ordering():
    """Test that membership statuses are ordered by sort_order then name."""
    # Clear existing data for this test
    MembershipStatus.objects.all().delete()

    # Create statuses in reverse order
    status_c = MembershipStatus.objects.create(name="C Member", sort_order=30)
    status_a = MembershipStatus.objects.create(name="A Member", sort_order=10)
    status_b = MembershipStatus.objects.create(name="B Member", sort_order=20)

    # Should be ordered by sort_order
    statuses = list(MembershipStatus.objects.all())
    assert statuses[0] == status_a
    assert statuses[1] == status_b
    assert statuses[2] == status_c


@pytest.mark.django_db(transaction=True)
def test_membership_status_ordering_by_name():
    """Test that membership statuses with same sort_order are ordered by name."""
    # Clear existing data for this test
    MembershipStatus.objects.all().delete()

    status_z = MembershipStatus.objects.create(name="Z Member", sort_order=10)
    status_a = MembershipStatus.objects.create(name="A Member", sort_order=10)
    status_m = MembershipStatus.objects.create(name="M Member", sort_order=10)

    # Should be ordered by name when sort_order is the same
    statuses = list(MembershipStatus.objects.all())
    assert statuses[0] == status_a
    assert statuses[1] == status_m
    assert statuses[2] == status_z


@pytest.mark.django_db(transaction=True)
def test_get_active_statuses():
    """Test the get_active_statuses class method."""
    # Clear existing data for this test
    MembershipStatus.objects.all().delete()

    # Create a mix of active and inactive statuses
    MembershipStatus.objects.create(name="Active 1", is_active=True)
    MembershipStatus.objects.create(name="Active 2", is_active=True)
    MembershipStatus.objects.create(name="Inactive 1", is_active=False)
    MembershipStatus.objects.create(name="Inactive 2", is_active=False)

    active_statuses = list(MembershipStatus.get_active_statuses())
    assert len(active_statuses) == 2
    assert "Active 1" in active_statuses
    assert "Active 2" in active_statuses
    assert "Inactive 1" not in active_statuses
    assert "Inactive 2" not in active_statuses


@pytest.mark.django_db(transaction=True)
def test_get_all_status_choices():
    """Test the get_all_status_choices class method."""
    # Clear existing data for this test
    MembershipStatus.objects.all().delete()

    # Create statuses with different sort orders
    MembershipStatus.objects.create(name="C Member", sort_order=30)
    MembershipStatus.objects.create(name="A Member", sort_order=10)
    MembershipStatus.objects.create(name="B Member", sort_order=20)

    choices = MembershipStatus.get_all_status_choices()

    # Should return tuples in correct order
    assert len(choices) == 3
    assert choices[0] == ("A Member", "A Member")
    assert choices[1] == ("B Member", "B Member")
    assert choices[2] == ("C Member", "C Member")


@pytest.mark.django_db
def test_membership_status_defaults():
    """Test default values for MembershipStatus fields."""
    status = MembershipStatus.objects.create(name="Test Status")

    assert status.is_active is True  # Default should be True
    assert status.sort_order == 100  # Default should be 100
    assert status.description == ""  # Default should be empty string
    assert status.created_at is not None
    assert status.updated_at is not None


@pytest.mark.django_db
def test_membership_status_deletion_protection():
    """Test that membership statuses cannot be deleted if members are using them."""
    from members.models import Member

    # Create a status and a member using it
    status = MembershipStatus.objects.create(
        name="Test Protected Status", is_active=True
    )
    Member.objects.create(
        username="test_member", membership_status="Test Protected Status"
    )

    # Try to delete the status - should fail
    with pytest.raises(ValidationError) as exc_info:
        status.delete()

    assert "Cannot delete membership status" in str(exc_info.value)
    assert "1 members currently have this status" in str(exc_info.value)

    # Status should still exist
    assert MembershipStatus.objects.filter(name="Test Protected Status").exists()


@pytest.mark.django_db
def test_membership_status_deletion_success():
    """Test that unused membership statuses can be deleted successfully."""
    # Create a status that no member uses
    status = MembershipStatus.objects.create(name="Unused Status", is_active=True)

    # Should be able to delete without error
    status.delete()

    # Status should be gone
    assert not MembershipStatus.objects.filter(name="Unused Status").exists()


@pytest.mark.django_db
def test_surge_threshold_defaults():
    """Test that surge thresholds have correct default values (Issue #403)."""
    config = SiteConfiguration.objects.create(
        club_name="Test Club", domain_name="test.org", club_abbreviation="TC"
    )
    assert config.tow_surge_threshold == 6
    assert config.instruction_surge_threshold == 4


@pytest.mark.django_db
def test_surge_threshold_custom_values():
    """Test setting custom surge threshold values (Issue #403)."""
    config = SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="test.org",
        club_abbreviation="TC",
        tow_surge_threshold=10,
        instruction_surge_threshold=5,
    )
    assert config.tow_surge_threshold == 10
    assert config.instruction_surge_threshold == 5


@pytest.mark.django_db
def test_surge_threshold_positive_integers():
    """Test that surge thresholds must be positive integers (Issue #403)."""
    config = SiteConfiguration.objects.create(
        club_name="Test Club", domain_name="test.org", club_abbreviation="TC"
    )

    # Should accept positive values
    config.tow_surge_threshold = 1
    config.instruction_surge_threshold = 1
    config.save()
    config.refresh_from_db()
    assert config.tow_surge_threshold == 1
    assert config.instruction_surge_threshold == 1

    # Zero should work (PositiveIntegerField allows 0)
    config.tow_surge_threshold = 0
    config.instruction_surge_threshold = 0
    config.save()
    config.refresh_from_db()
    assert config.tow_surge_threshold == 0
    assert config.instruction_surge_threshold == 0
