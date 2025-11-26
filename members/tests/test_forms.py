from io import BytesIO

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from members.forms import BiographyForm, MemberProfilePhotoForm, SetPasswordForm

User = get_user_model()


def create_test_image(width=400, height=400, format="JPEG"):
    """Helper to create a test image as an uploadable file."""
    img = Image.new("RGB", (width, height), color="blue")
    buffer = BytesIO()
    img.save(buffer, format=format)
    buffer.seek(0)
    return SimpleUploadedFile(
        name="test_photo.jpg", content=buffer.getvalue(), content_type="image/jpeg"
    )


def test_set_password_form_valid():
    form = SetPasswordForm(
        data={"new_password1": "testing123", "new_password2": "testing123"}
    )
    assert form.is_valid()


def test_set_password_form_mismatch():
    form = SetPasswordForm(data={"new_password1": "abc123", "new_password2": "xyz789"})
    assert not form.is_valid()
    assert "__all__" in form.errors
    assert "Passwords do not match" in form.errors["__all__"][0]


@pytest.mark.django_db
def test_biography_form_accepts_html(django_user_model):
    user = django_user_model.objects.create_user(
        username="tester",
        password="oldpass",
        membership_status="Full Member",  # ✅ Must be one of the items in DEFAULT_ACTIVE_STATUSES
        is_superuser=False,
    )
    form = BiographyForm(data={"content": "<p>Hello, world!</p>"})
    assert form.is_valid()
    instance = form.save(commit=False)
    instance.member = user
    instance.save()
    assert instance.content == "<p>Hello, world!</p>"


# =============================================================================
# MemberProfilePhotoForm Tests (Issue #286 - Thumbnail Generation)
# =============================================================================


@pytest.mark.django_db
class TestMemberProfilePhotoForm:
    """Tests for MemberProfilePhotoForm thumbnail generation."""

    def test_form_generates_thumbnails_on_upload(self, django_user_model, settings):
        """Form should generate medium and small thumbnails when photo is uploaded."""
        settings.TESTING = True  # Skip avatar generation
        member = django_user_model.objects.create_user(
            username="photo_test_user",
            password="testpass",
            membership_status="Full Member",
        )

        uploaded_file = create_test_image(600, 600)
        form = MemberProfilePhotoForm(
            data={}, files={"profile_photo": uploaded_file}, instance=member
        )

        assert form.is_valid()
        saved_member = form.save()

        # Verify all three photo fields are populated
        assert saved_member.profile_photo
        assert saved_member.profile_photo_medium
        assert saved_member.profile_photo_small

        # Clean up uploaded files to avoid storage bloat
        if saved_member.profile_photo:
            saved_member.profile_photo.delete(save=False)
        if saved_member.profile_photo_medium:
            saved_member.profile_photo_medium.delete(save=False)
        if saved_member.profile_photo_small:
            saved_member.profile_photo_small.delete(save=False)

    def test_form_rejects_invalid_aspect_ratio(self, django_user_model, settings):
        """Form should reject images with extreme aspect ratios."""
        settings.TESTING = True
        member = django_user_model.objects.create_user(
            username="aspect_test_user",
            password="testpass",
            membership_status="Full Member",
        )

        # Create a panorama image (3:1 aspect ratio)
        uploaded_file = create_test_image(900, 300)
        form = MemberProfilePhotoForm(
            data={}, files={"profile_photo": uploaded_file}, instance=member
        )

        assert form.is_valid()  # Form validation passes
        # But save should raise ValidationError (no files saved, so no cleanup needed)
        with pytest.raises(ValidationError):
            form.save()

    def test_form_works_without_photo_upload(self, django_user_model, settings):
        """Form should work correctly when no photo is uploaded."""
        settings.TESTING = True
        member = django_user_model.objects.create_user(
            username="no_photo_user",
            password="testpass",
            membership_status="Full Member",
        )

        form = MemberProfilePhotoForm(data={}, instance=member)
        assert form.is_valid()
        saved_member = form.save()
        assert saved_member.pk == member.pk
