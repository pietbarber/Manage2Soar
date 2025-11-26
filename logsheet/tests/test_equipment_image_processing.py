"""
Tests for equipment (glider and towplane) photo thumbnail generation.

Tests the image processing utilities for creating square thumbnails
from equipment photos, with more lenient aspect ratio requirements
than profile photos.
"""

from io import BytesIO

import pytest
from PIL import Image

from logsheet.utils.image_processing import (
    THUMBNAIL_MEDIUM,
    THUMBNAIL_SMALL,
    create_square_thumbnail,
    generate_equipment_thumbnails,
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
        result = create_square_thumbnail(img, 100)

        assert result.size == (100, 100)

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
        """Should create 100x100 thumbnails for maintenance list."""
        img = Image.new("RGB", (500, 500), color="red")
        result = create_square_thumbnail(img, THUMBNAIL_SMALL)

        assert result.size == (100, 100)

    def test_medium_thumbnail_size(self):
        """Should create 150x150 thumbnails for equipment list."""
        img = Image.new("RGB", (500, 500), color="red")
        result = create_square_thumbnail(img, THUMBNAIL_MEDIUM)

        assert result.size == (150, 150)


class TestGenerateEquipmentThumbnails:
    """Tests for generate_equipment_thumbnails function."""

    def test_generates_all_three_sizes(self):
        """Should generate original, medium, and small versions."""
        uploaded = create_test_image(600, 400)
        result = generate_equipment_thumbnails(uploaded)

        assert "original" in result
        assert "medium" in result
        assert "small" in result

    def test_original_maintains_aspect_ratio(self):
        """Original should resize but maintain aspect ratio."""
        uploaded = create_test_image(1200, 800)
        result = generate_equipment_thumbnails(uploaded)

        # Original should be resized but maintain aspect ratio
        original_img = Image.open(result["original"])
        assert original_img.size[0] <= 800
        assert original_img.size[1] <= 600

    def test_medium_is_150x150(self):
        """Medium thumbnail should be exactly 150x150."""
        uploaded = create_test_image(600, 400)
        result = generate_equipment_thumbnails(uploaded)

        medium_img = Image.open(result["medium"])
        assert medium_img.size == (150, 150)

    def test_small_is_100x100(self):
        """Small thumbnail should be exactly 100x100."""
        uploaded = create_test_image(600, 400)
        result = generate_equipment_thumbnails(uploaded)

        small_img = Image.open(result["small"])
        assert small_img.size == (100, 100)

    def test_accepts_wide_landscape_aircraft_photos(self):
        """Should accept 2.5:1 aspect ratio (common for aircraft photos)."""
        uploaded = create_test_image(1000, 400)  # 2.5:1 ratio
        result = generate_equipment_thumbnails(uploaded)

        assert "original" in result

    def test_rejects_extreme_panorama_aspect_ratio(self):
        """Should reject images that are too wide (>3:1 panoramas)."""
        # 4:1 aspect ratio should be rejected
        uploaded = create_test_image(1200, 300)

        with pytest.raises(ValueError) as exc_info:
            generate_equipment_thumbnails(uploaded)

        assert "aspect ratio" in str(exc_info.value).lower()

    def test_rejects_extreme_portrait_aspect_ratio(self):
        """Should reject images that are too tall (skyscrapers)."""
        # 1:3 aspect ratio should be rejected
        uploaded = create_test_image(300, 900)

        with pytest.raises(ValueError) as exc_info:
            generate_equipment_thumbnails(uploaded)

        assert "aspect ratio" in str(exc_info.value).lower()

    def test_accepts_3_to_1_landscape(self):
        """Should accept exactly 3:1 landscape (edge case)."""
        uploaded = create_test_image(900, 300)  # exactly 3:1
        result = generate_equipment_thumbnails(uploaded)

        assert "original" in result

    def test_converts_png_to_jpeg(self):
        """Should convert PNG uploads to JPEG for consistency."""
        # Create a PNG image
        img = Image.new("RGB", (400, 300), color="blue")
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        buffer.name = "test_image.png"

        result = generate_equipment_thumbnails(buffer)

        # All outputs should be valid JPEG images
        for key in ["original", "medium", "small"]:
            result_img = Image.open(result[key])
            assert result_img.format == "JPEG"

    def test_rejects_invalid_file(self):
        """Should raise ValueError for non-image files."""
        buffer = BytesIO(b"not an image file")
        buffer.name = "fake.jpg"

        with pytest.raises(ValueError) as exc_info:
            generate_equipment_thumbnails(buffer)

        assert "invalid image" in str(exc_info.value).lower()

    def test_handles_file_seek(self):
        """Should handle files that have already been read."""
        uploaded = create_test_image(400, 300)
        # Read the file to move cursor to end
        uploaded.read()
        # Function should seek back to beginning
        result = generate_equipment_thumbnails(uploaded)

        assert "original" in result
