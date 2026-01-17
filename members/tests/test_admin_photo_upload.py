"""
Tests for admin photo upload thumbnail generation.

Issue #479: When uploading photos via admin interface, thumbnails should
be generated just like when members upload their own photos.
"""

from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.admin.sites import AdminSite
from django.core.exceptions import ValidationError
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

        # Create a real test image using Django's file handling
        from django.core.files.uploadedfile import SimpleUploadedFile

        test_image = create_test_image(400, 400)
        uploaded_file = SimpleUploadedFile(
            "test_photo.jpg", test_image.read(), content_type="image/jpeg"
        )
        test_member.profile_photo = uploaded_file

        with patch(
            "members.admin.generate_profile_thumbnails"
        ) as mock_generate_thumbnails:
            # Set up mock return value
            mock_original = BytesIO(b"original_data")
            mock_original.name = "original.jpg"
            mock_medium = BytesIO(b"medium_data")
            mock_medium.name = "medium.jpg"
            mock_small = BytesIO(b"small_data")
            mock_small.name = "small.jpg"

            mock_generate_thumbnails.return_value = {
                "original": mock_original,
                "medium": mock_medium,
                "small": mock_small,
            }

            # Mock the ImageField.save() method to avoid actual file I/O
            with patch.object(test_member.profile_photo, "save") as mock_photo_save:
                with patch.object(
                    test_member.profile_photo_medium, "save"
                ) as mock_medium_save:
                    with patch.object(
                        test_member.profile_photo_small, "save"
                    ) as mock_small_save:
                        # Call save_model
                        member_admin.save_model(request, test_member, form, change=True)

                        # Verify generate_profile_thumbnails was called with the uploaded photo
                        mock_generate_thumbnails.assert_called_once()

                        # Verify the save() method was called on thumbnail fields
                        # Note: profile_photo.save() is called twice - once for the processed
                        # original and once during obj.save(). We just verify it was called.
                        assert mock_photo_save.called
                        mock_medium_save.assert_called_once()
                        mock_small_save.assert_called_once()

                        # Verify the first call to profile_photo.save() was with processed original
                        first_call_args = mock_photo_save.call_args_list[0]
                        assert first_call_args[0][0] == "test_photo.jpg"  # filename
                        assert first_call_args[0][1] == mock_original  # BytesIO content
                        assert first_call_args[1]["save"] is False  # save=False

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

    def test_save_model_raises_validation_error_on_processing_failure(
        self, member_admin, test_member
    ):
        """Verify ValidationError is raised when thumbnail generation fails."""
        request = MagicMock()
        form = MagicMock()
        form.changed_data = ["profile_photo"]

        # Create a real test image using Django's file handling
        from django.core.files.uploadedfile import SimpleUploadedFile

        test_image = create_test_image(400, 400)
        uploaded_file = SimpleUploadedFile(
            "test_photo.jpg", test_image.read(), content_type="image/jpeg"
        )
        test_member.profile_photo = uploaded_file

        with patch(
            "members.admin.generate_profile_thumbnails"
        ) as mock_generate_thumbnails:
            # Simulate thumbnail generation failure
            mock_generate_thumbnails.side_effect = ValueError(
                "Invalid image format or aspect ratio"
            )

            # Should raise ValidationError with helpful message
            with pytest.raises(ValidationError) as exc_info:
                member_admin.save_model(request, test_member, form, change=True)

            # Verify error message is helpful for admins
            assert "Photo processing failed" in str(exc_info.value)
            assert "Invalid image format" in str(exc_info.value)
