"""
Tests for admin photo upload thumbnail generation.

Issue #479: When uploading photos via admin interface, thumbnails should
be generated just like when members upload their own photos.
"""

from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.admin.sites import AdminSite
from PIL import Image

from members.admin import MemberAdmin
from members.models import Member


def create_test_image(width=400, height=400, color="red", format="JPEG"):
    """Helper to create a test image in memory."""
    img = Image.new("RGB", (width, height), color=color)
    buffer = BytesIO()
    img.save(buffer, format=format)
    buffer.seek(0)
    buffer.name = "test_photo.jpg"
    return buffer


@pytest.fixture
def member_admin():
    """Create a MemberAdmin instance for testing."""
    site = AdminSite()
    return MemberAdmin(Member, site)


@pytest.fixture
def test_member(db):
    """Create a test member."""
    return Member.objects.create(
        username="testmember",
        email="test@example.com",
        first_name="Test",
        last_name="Member",
    )


@pytest.mark.django_db
class TestAdminPhotoUpload:
    """Tests for admin photo upload thumbnail generation."""

    def test_save_model_generates_thumbnails_on_photo_upload(
        self, member_admin, test_member
    ):
        """Issue #479: Verify thumbnails are generated when photo uploaded via admin."""
        # Create a mock request
        request = MagicMock()

        # Create a mock form with changed_data indicating photo was uploaded
        form = MagicMock()
        form.changed_data = ["profile_photo"]

        # Create a test image and attach to member
        test_image = create_test_image(400, 400)
        test_member.profile_photo = test_image

        with patch(
            "members.admin.generate_profile_thumbnails"
        ) as mock_generate_thumbnails:
            # Set up mock return value
            mock_generate_thumbnails.return_value = {
                "original": BytesIO(b"original"),
                "medium": BytesIO(b"medium"),
                "small": BytesIO(b"small"),
            }

            # Call save_model
            member_admin.save_model(request, test_member, form, change=True)

            # Verify generate_profile_thumbnails was called
            mock_generate_thumbnails.assert_called_once()

    def test_save_model_skips_thumbnails_when_no_photo_change(
        self, member_admin, test_member
    ):
        """Verify thumbnails are NOT generated if photo wasn't changed."""
        request = MagicMock()

        # Form without profile_photo in changed_data
        form = MagicMock()
        form.changed_data = ["first_name", "last_name"]

        with patch(
            "members.admin.generate_profile_thumbnails"
        ) as mock_generate_thumbnails:
            member_admin.save_model(request, test_member, form, change=True)

            # Should NOT call generate_profile_thumbnails
            mock_generate_thumbnails.assert_not_called()

    def test_save_model_skips_thumbnails_when_photo_cleared(
        self, member_admin, test_member
    ):
        """Verify thumbnails are NOT generated if photo was cleared (None)."""
        request = MagicMock()

        form = MagicMock()
        form.changed_data = ["profile_photo"]

        # No photo (cleared)
        test_member.profile_photo = None

        with patch(
            "members.admin.generate_profile_thumbnails"
        ) as mock_generate_thumbnails:
            member_admin.save_model(request, test_member, form, change=True)

            # Should NOT call generate_profile_thumbnails
            mock_generate_thumbnails.assert_not_called()
