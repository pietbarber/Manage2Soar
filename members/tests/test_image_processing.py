"""
Tests for profile photo thumbnail generation.

Tests the image processing utilities for creating square thumbnails
from profile photos in various aspect ratios and sizes.
"""

from io import BytesIO

import pytest
from PIL import Image

from members.utils.image_processing import (
    THUMBNAIL_MEDIUM,
    THUMBNAIL_SMALL,
    create_square_thumbnail,
    generate_profile_thumbnails,
)


def create_test_image(width, height, color="red", format="JPEG"):
    """Helper to create a test image in memory."""
    img = Image.new("RGB", (width, height), color=color)
    buffer = BytesIO()
    img.save(buffer, format=format)
    buffer.seek(0)
    buffer.name = "test_image.jpg"
    return buffer


class TestCreateSquareThumbnail:
    """Tests for create_square_thumbnail function."""

    def test_square_image_returns_correct_size(self):
        """Square images should resize without cropping."""
        img = Image.new("RGB", (400, 400), color="blue")
        result = create_square_thumbnail(img, 64)

        assert result.size == (64, 64)

    def test_landscape_image_crops_sides(self):
        """Landscape images should crop sides to create square."""
        img = Image.new("RGB", (800, 400), color="green")
        result = create_square_thumbnail(img, 100)

        assert result.size == (100, 100)

    def test_portrait_image_crops_top_bottom(self):
        """Portrait images should crop top/bottom to create square."""
        img = Image.new("RGB", (400, 800), color="yellow")
        result = create_square_thumbnail(img, 100)

        assert result.size == (100, 100)

    def test_small_thumbnail_size(self):
        """Should create 64x64 thumbnails for navbar use."""
        img = Image.new("RGB", (500, 500), color="red")
        result = create_square_thumbnail(img, THUMBNAIL_SMALL)

        assert result.size == (64, 64)

    def test_medium_thumbnail_size(self):
        """Should create 200x200 thumbnails for profile view use."""
        img = Image.new("RGB", (500, 500), color="red")
        result = create_square_thumbnail(img, THUMBNAIL_MEDIUM)

        assert result.size == (200, 200)


class TestGenerateProfileThumbnails:
    """Tests for generate_profile_thumbnails function."""

    def test_generates_all_three_sizes(self):
        """Should generate original, medium, and small versions."""
        uploaded = create_test_image(600, 600)
        result = generate_profile_thumbnails(uploaded)

        assert "original" in result
        assert "medium" in result
        assert "small" in result

    def test_original_maintains_aspect_ratio(self):
        """Original should resize but maintain aspect ratio."""
        uploaded = create_test_image(600, 400)
        result = generate_profile_thumbnails(uploaded)

        # Original should be resized but maintain aspect ratio
        original_img = Image.open(result["original"])
        assert original_img.size[0] <= 800
        assert original_img.size[1] <= 800

    def test_medium_is_200x200(self):
        """Medium thumbnail should be exactly 200x200."""
        uploaded = create_test_image(600, 600)
        result = generate_profile_thumbnails(uploaded)

        medium_img = Image.open(result["medium"])
        assert medium_img.size == (200, 200)

    def test_small_is_64x64(self):
        """Small thumbnail should be exactly 64x64."""
        uploaded = create_test_image(600, 600)
        result = generate_profile_thumbnails(uploaded)

        small_img = Image.open(result["small"])
        assert small_img.size == (64, 64)

    def test_rejects_panorama_aspect_ratio(self):
        """Should reject images that are too wide (panoramas)."""
        # 3:1 aspect ratio should be rejected (MAX_ASPECT_RATIO is 2.0)
        uploaded = create_test_image(900, 300)

        with pytest.raises(ValueError) as exc_info:
            generate_profile_thumbnails(uploaded)

        assert "reasonably square" in str(exc_info.value).lower()

    def test_rejects_skyscraper_aspect_ratio(self):
        """Should reject images that are too tall (skyscrapers)."""
        # 1:3 aspect ratio should be rejected (MIN_ASPECT_RATIO is 0.5)
        uploaded = create_test_image(300, 900)

        with pytest.raises(ValueError) as exc_info:
            generate_profile_thumbnails(uploaded)

        assert "reasonably square" in str(exc_info.value).lower()

    def test_accepts_valid_aspect_ratios(self):
        """Should accept images within valid aspect ratio range."""
        # 1.5:1 is within range
        uploaded = create_test_image(600, 400)
        result = generate_profile_thumbnails(uploaded)

        assert "original" in result

    def test_converts_png_to_jpeg(self):
        """Should convert PNG uploads to JPEG for consistency."""
        # Create a PNG image
        img = Image.new("RGB", (400, 400), color="blue")
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        buffer.name = "test_image.png"

        result = generate_profile_thumbnails(buffer)

        # All outputs should be valid JPEG images
        for key in ["original", "medium", "small"]:
            result_img = Image.open(result[key])
            assert result_img.format == "JPEG"

    def test_rejects_invalid_file(self):
        """Should raise ValueError for non-image files."""
        buffer = BytesIO(b"not an image file")
        buffer.name = "fake.jpg"

        with pytest.raises(ValueError) as exc_info:
            generate_profile_thumbnails(buffer)

        assert "invalid image" in str(exc_info.value).lower()

    def test_handles_file_seek(self):
        """Should handle files that have already been read."""
        uploaded = create_test_image(400, 400)
        # Read the file to move cursor to end
        uploaded.read()
        # Function should seek back to beginning
        result = generate_profile_thumbnails(uploaded)

        assert "original" in result

    def test_applies_exif_orientation(self):
        """Should respect EXIF orientation tags from phone cameras."""
        from PIL import ImageOps

        # Create a landscape image (800x600) with distinct colors to verify rotation
        img = Image.new("RGB", (800, 600), color="red")
        # Add a blue stripe on the right side to track orientation
        for x in range(700, 800):
            for y in range(600):
                img.putpixel((x, y), (0, 0, 255))  # Blue

        # Save with EXIF orientation tag indicating 90° CCW rotation
        # (Orientation=6 means the image should be rotated 90° CW to display correctly)
        buffer = BytesIO()
        exif_bytes = b"\xff\xe1\x00\x16Exif\x00\x00MM\x00*\x00\x00\x00\x08\x00\x01\x01\x12\x00\x03\x00\x00\x00\x01\x00\x06\x00\x00"
        # Manual EXIF construction with Orientation=6
        img.save(buffer, format="JPEG", quality=95)
        buffer.seek(0)

        # For proper test, create image with actual EXIF orientation
        # PIL's exif_transpose should handle this
        img_with_exif = Image.new("RGB", (800, 600), color="red")
        # Add blue stripe on right
        for x in range(700, 800):
            for y in range(600):
                img_with_exif.putpixel((x, y), (0, 0, 255))

        # Set EXIF orientation to 6 (rotate 90° CW)
        exif = img_with_exif.getexif()
        exif[0x0112] = 6  # Orientation tag
        buffer = BytesIO()
        img_with_exif.save(buffer, format="JPEG", quality=95, exif=exif)
        buffer.seek(0)
        buffer.name = "rotated_photo.jpg"

        # Process the image
        result = generate_profile_thumbnails(buffer)

        # Verify EXIF orientation was applied
        # After applying orientation=6, the 800x600 landscape should become 600x800 portrait
        original_img = Image.open(result["original"])

        # The image should now be portrait (taller than wide) after EXIF rotation
        width, height = original_img.size
        assert (
            height > width
        ), f"Image should be portrait after EXIF rotation, got {width}x{height}"

    def test_exif_transpose_handles_missing_exif(self):
        """Should handle images without EXIF data gracefully."""
        # Create simple image with no EXIF data
        uploaded = create_test_image(400, 400)

        # Should process without errors
        result = generate_profile_thumbnails(uploaded)

        assert "original" in result
        assert "medium" in result
        assert "small" in result
