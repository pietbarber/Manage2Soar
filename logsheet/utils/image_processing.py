"""
Image processing utilities for equipment (glider and towplane) photos.

Provides functions for creating thumbnails from uploaded equipment photos.
Equipment photos typically have more varied aspect ratios than profile photos,
so the aspect ratio constraints are more lenient.
"""

import logging
from io import BytesIO

from django.core.files.base import ContentFile
from PIL import Image

logger = logging.getLogger(__name__)

# Configurable settings for original/large image
MAX_WIDTH = 800
MAX_HEIGHT = 600

# Equipment photos can be wider since aircraft photos are often landscape
MIN_ASPECT_RATIO = 0.5  # Tallest allowed is 2:1 (portrait)
MAX_ASPECT_RATIO = 3.0  # Widest allowed is 3:1 (landscape - common for aircraft)

# Thumbnail sizes
THUMBNAIL_SMALL = 100  # For list views (100x100)
THUMBNAIL_MEDIUM = 150  # For equipment list (150x150)


def create_square_thumbnail(image, size):
    """
    Create a square thumbnail from an image by center-cropping then resizing.

    This ensures thumbnails are always square and properly sized for
    consistent display in equipment lists.

    Args:
        image: PIL Image object
        size: Target size in pixels (will be size x size)

    Returns:
        PIL Image object (square, sized to `size x size`)
    """
    width, height = image.size

    # Determine the size of the square crop (centered)
    if width > height:
        # Landscape: crop sides
        left = (width - height) // 2
        top = 0
        right = left + height
        bottom = height
    else:
        # Portrait or square: crop top/bottom
        left = 0
        top = (height - width) // 2
        right = width
        bottom = top + width

    # Crop to square
    cropped = image.crop((left, top, right, bottom))

    # Resize to target size with high-quality resampling
    thumbnail = cropped.resize((size, size), Image.Resampling.LANCZOS)

    return thumbnail


def generate_equipment_thumbnails(uploaded_file):
    """
    Generate all required equipment photo sizes from an uploaded image.

    Creates three versions:
    - Original: Max 800x600, maintains aspect ratio
    - Medium: 150x150 square thumbnail for equipment list
    - Small: 100x100 square thumbnail for maintenance list

    Args:
        uploaded_file: File-like object containing the uploaded image

    Returns:
        dict with keys 'original', 'medium', 'small', each containing
        a ContentFile ready to be saved to an ImageField

    Raises:
        ValueError: If the image is invalid or has unacceptable aspect ratio
    """
    try:
        # Seek to beginning in case file was already read
        if hasattr(uploaded_file, "seek"):
            uploaded_file.seek(0)
        img = Image.open(uploaded_file)
        # Always convert to RGB and save as JPEG for consistency
        img = img.convert("RGB")
    except Exception as e:
        raise ValueError(f"Invalid image file: {e}")

    # Check aspect ratio
    width, height = img.size
    aspect_ratio = width / height
    if not (MIN_ASPECT_RATIO <= aspect_ratio <= MAX_ASPECT_RATIO):
        raise ValueError(
            "Image aspect ratio is too extreme. "
            "Please use a photo that is not too narrow or too wide."
        )

    result = {}

    # Create original/large version (maintains aspect ratio)
    original = img.copy()
    if width > MAX_WIDTH or height > MAX_HEIGHT:
        original.thumbnail((MAX_WIDTH, MAX_HEIGHT), Image.Resampling.LANCZOS)

    original_buffer = BytesIO()
    original.save(original_buffer, format="JPEG", quality=85, optimize=True)
    result["original"] = ContentFile(original_buffer.getvalue())

    # Create medium thumbnail (square crop)
    medium = create_square_thumbnail(img, THUMBNAIL_MEDIUM)
    medium_buffer = BytesIO()
    medium.save(medium_buffer, format="JPEG", quality=85, optimize=True)
    result["medium"] = ContentFile(medium_buffer.getvalue())

    # Create small thumbnail (square crop)
    small = create_square_thumbnail(img, THUMBNAIL_SMALL)
    small_buffer = BytesIO()
    small.save(small_buffer, format="JPEG", quality=85, optimize=True)
    result["small"] = ContentFile(small_buffer.getvalue())

    logger.info(
        f"Generated equipment thumbnails: original={original.size}, "
        f"medium={THUMBNAIL_MEDIUM}x{THUMBNAIL_MEDIUM}, "
        f"small={THUMBNAIL_SMALL}x{THUMBNAIL_SMALL}"
    )

    return result
