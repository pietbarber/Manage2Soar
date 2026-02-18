import io
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.exceptions import ValidationError

from siteconfig.models import MembershipStatus, SiteConfiguration
from utils.favicon import PWA_CLUB_ICON_NAME

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


@pytest.mark.django_db
def test_manual_whitelist_field():
    """Test that manual_whitelist field can be created and updated (Issue #492)."""
    config = SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="example.org",
        club_abbreviation="TC",
        manual_whitelist="user1@example.com\nuser2@example.com",
    )
    assert config.manual_whitelist == "user1@example.com\nuser2@example.com"


@pytest.mark.django_db
def test_manual_whitelist_default_empty():
    """Test that manual_whitelist defaults to empty string (Issue #492)."""
    config = SiteConfiguration.objects.create(
        club_name="Test Club", domain_name="example.org", club_abbreviation="TC"
    )
    assert config.manual_whitelist == ""


@pytest.mark.django_db
def test_manual_whitelist_persists():
    """Test that manual_whitelist value persists across save/load (Issue #492)."""
    config = SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="example.org",
        club_abbreviation="TC",
        manual_whitelist="admin@example.com\nwebmaster@example.org",
    )
    config.refresh_from_db()
    assert config.manual_whitelist == "admin@example.com\nwebmaster@example.org"

    # Test updating
    config.manual_whitelist = "new@example.com"
    config.save()
    config.refresh_from_db()
    assert config.manual_whitelist == "new@example.com"


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

    # Zero should NOT work (business logic: minimum is 1)
    config.tow_surge_threshold = 0
    config.instruction_surge_threshold = 0
    with pytest.raises(ValidationError):
        config.full_clean()

    # After failed validation, values should remain unchanged in DB
    config.refresh_from_db()
    assert config.tow_surge_threshold == 1
    assert config.instruction_surge_threshold == 1


# Quick Altitude Buttons Tests (Issue #467)
@pytest.mark.django_db
def test_quick_altitude_list_default():
    """Test default altitude button configuration (2000,3000)."""
    config = SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="test.com",
        club_abbreviation="TC",
        quick_altitude_buttons="2000,3000",
    )
    result = config.get_quick_altitude_list()
    assert result == [(2000, "2K"), (3000, "3K")]


@pytest.mark.django_db
def test_quick_altitude_list_custom_formatting():
    """Test altitude label formatting for various values."""
    config = SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="test.com",
        club_abbreviation="TC",
        quick_altitude_buttons="300,1000,1500,2000,3000",
    )
    result = config.get_quick_altitude_list()
    assert result == [
        (300, "300"),  # Below 1000 -> plain number
        (1000, "1K"),  # Exactly 1000 -> "1K"
        (1500, "1.5K"),  # 1500 -> "1.5K"
        (2000, "2K"),  # 2000 -> "2K"
        (3000, "3K"),  # 3000 -> "3K"
    ]


@pytest.mark.django_db
def test_quick_altitude_list_edge_cases():
    """Test edge cases: empty string, whitespace, invalid values."""
    config = SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="test.com",
        club_abbreviation="TC",
    )

    # Empty string
    config.quick_altitude_buttons = ""
    assert config.get_quick_altitude_list() == []

    # Only whitespace
    config.quick_altitude_buttons = "  ,  ,  "
    assert config.get_quick_altitude_list() == []

    # Invalid values mixed with valid
    config.quick_altitude_buttons = "invalid,2000,abc,3000"
    result = config.get_quick_altitude_list()
    assert result == [(2000, "2K"), (3000, "3K")]

    # All invalid values
    config.quick_altitude_buttons = "abc,def,xyz"
    assert config.get_quick_altitude_list() == []


@pytest.mark.django_db
def test_quick_altitude_list_with_spaces():
    """Test that spaces around values are handled correctly."""
    config = SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="test.com",
        club_abbreviation="TC",
        quick_altitude_buttons="500, 1200,  2500  ",
    )
    result = config.get_quick_altitude_list()
    assert result == [
        (500, "500"),
        (1200, "1.2K"),
        (2500, "2.5K"),
    ]


@pytest.mark.django_db
def test_quick_altitude_validation_positive_integers():
    """Test that clean() validates altitude values are positive."""
    config = SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="test.com",
        club_abbreviation="TC",
    )

    # Negative values should fail validation
    config.quick_altitude_buttons = "2000,-100,3000"
    with pytest.raises(ValidationError) as exc_info:
        config.full_clean()
    assert "quick_altitude_buttons" in exc_info.value.error_dict
    assert "positive integers" in str(exc_info.value)

    # Non-integer values should fail validation
    config.quick_altitude_buttons = "2000,abc,3000"
    with pytest.raises(ValidationError) as exc_info:
        config.full_clean()
    assert "quick_altitude_buttons" in exc_info.value.error_dict
    assert "must be integers" in str(exc_info.value)

    # Values over 7000 should fail validation
    config.quick_altitude_buttons = "2000,8000,3000"
    with pytest.raises(ValidationError) as exc_info:
        config.full_clean()
    assert "quick_altitude_buttons" in exc_info.value.error_dict
    assert "7000 feet or less" in str(exc_info.value)

    # Valid values should pass
    config.quick_altitude_buttons = "300,1000,2000,3000"
    config.full_clean()  # Should not raise
    config.save()
    config.refresh_from_db()
    assert config.quick_altitude_buttons == "300,1000,2000,3000"


# ---------------------------------------------------------------------------
# PWA icon backfill and logo-removal tests
# ---------------------------------------------------------------------------


def _make_tiny_png_bytes():
    """Return bytes for a minimal 10×10 RGBA PNG."""
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGBA", (10, 10), color=(30, 100, 200, 255)).save(buf, format="PNG")
    return buf.getvalue()


@pytest.mark.django_db
class TestPwaIconBackfill:
    """Tests for the backfill logic that generates pwa-icon-club.png for
    pre-existing installations where a club logo exists but the PWA icon
    was never generated."""

    def setup_method(self):
        cache.delete("pwa_club_icon_url")

    def test_backfill_generates_pwa_icon_when_logo_exists_and_icon_missing(self):
        """When saving a SiteConfiguration without a logo change, if the PWA
        icon does not yet exist in storage, it should be generated and saved."""
        config = SiteConfiguration.objects.create(
            club_name="Test Club",
            domain_name="test.com",
            club_abbreviation="TC",
        )
        # Simulate a pre-existing logo (set directly in the DB so that
        # the next save sees the same logo name → is_new_logo=False → backfill branch).
        SiteConfiguration.objects.filter(pk=config.pk).update(
            club_logo="logos/fake_logo.png"
        )
        config.refresh_from_db()

        saved_files = {}

        def fake_save(name, content, **kwargs):
            saved_files[name] = content.read()
            return name

        logo_bytes = _make_tiny_png_bytes()
        # Patch club_logo.open() at the instance level so we can feed test bytes
        # without touching the real storage backend.
        ctx_manager = MagicMock()
        ctx_manager.__enter__ = lambda s: io.BytesIO(logo_bytes)
        ctx_manager.__exit__ = MagicMock(return_value=False)

        with patch.object(config.club_logo, "open", return_value=ctx_manager), patch(
            "django.core.files.storage.default_storage.exists", return_value=False
        ), patch(
            "django.core.files.storage.default_storage.save", side_effect=fake_save
        ):
            config.save()

        assert (
            PWA_CLUB_ICON_NAME in saved_files
        ), "Backfill should save pwa-icon-club.png when logo exists but icon is missing"
        # Verify it's a valid 192×192 PNG
        from PIL import Image

        img = Image.open(io.BytesIO(saved_files[PWA_CLUB_ICON_NAME]))
        assert img.size == (192, 192)

    def test_backfill_does_not_overwrite_existing_pwa_icon(self):
        """When the PWA icon already exists in storage, the backfill should
        NOT overwrite it (no unnecessary network write)."""
        config = SiteConfiguration.objects.create(
            club_name="Test Club",
            domain_name="test.com",
            club_abbreviation="TC",
        )
        # Same pre-existing-logo setup so is_new_logo=False
        SiteConfiguration.objects.filter(pk=config.pk).update(
            club_logo="logos/fake_logo.png"
        )
        config.refresh_from_db()

        saved_files = {}

        def fake_save(name, content, **kwargs):
            saved_files[name] = content
            return name

        logo_bytes = _make_tiny_png_bytes()
        ctx_manager = MagicMock()
        ctx_manager.__enter__ = lambda s: io.BytesIO(logo_bytes)
        ctx_manager.__exit__ = MagicMock(return_value=False)

        with patch.object(config.club_logo, "open", return_value=ctx_manager), patch(
            "django.core.files.storage.default_storage.exists", return_value=True
        ), patch(
            "django.core.files.storage.default_storage.save", side_effect=fake_save
        ):
            config.save()

        # PWA icon already existed → no save should be triggered for it
        assert (
            PWA_CLUB_ICON_NAME not in saved_files
        ), "Backfill should not overwrite an already-present pwa-icon-club.png"

    def test_logo_removal_deletes_pwa_icon_and_favicon(self):
        """When the club logo is cleared, pwa-icon-club.png and favicon.ico
        should be deleted from storage and the cache key invalidated."""
        config = SiteConfiguration.objects.create(
            club_name="Test Club",
            domain_name="test.com",
            club_abbreviation="TC",
        )
        # Simulate that a logo was previously set so is_new_logo=True on clear
        SiteConfiguration.objects.filter(pk=config.pk).update(club_logo="old_logo.png")
        config.refresh_from_db()

        deleted_files = []
        cache.set("pwa_club_icon_url", "http://example.com/old-icon.png", 300)

        def fake_delete(name):
            deleted_files.append(name)

        with patch(
            "django.core.files.storage.default_storage.exists", return_value=True
        ), patch(
            "django.core.files.storage.default_storage.delete", side_effect=fake_delete
        ):
            # Clear the logo
            config.club_logo = None
            config.save()

        assert "favicon.ico" in deleted_files
        assert PWA_CLUB_ICON_NAME in deleted_files
        # Cache key should have been cleared
        assert cache.get("pwa_club_icon_url") is None
