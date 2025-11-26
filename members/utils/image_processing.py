import logging
import os
from io import BytesIO

from django.core.files.base import ContentFile
from PIL import Image

logger = logging.getLogger(__name__)

# Configurable settings for original/large image
MAX_WIDTH = 800
MAX_HEIGHT = 800
MIN_ASPECT_RATIO = 0.5  # Tallest allowed is 2:1 (portrait)
MAX_ASPECT_RATIO = 2.0  # Widest allowed is 2:1 (landscape)

# Thumbnail sizes - square crop for consistent display
THUMBNAIL_SMALL = 64  # For navbar, small bubbles
THUMBNAIL_MEDIUM = 200  # For member profile view, cards


def resize_and_crop_profile_photo(uploaded_file):
    """
    Resizes and checks aspect ratio of uploaded profile photo.
    Returns a ContentFile ready to be saved, or raises ValueError.
    """
    try:
        img = Image.open(uploaded_file)
        img_format = img.format or "JPEG"  # Default to JPEG if format missing
        img = img.convert("RGB")  # Always save in RGB for JPEG/PNG safety
    except Exception as e:
        raise ValueError(f"Invalid image file: {e}")

    # Check aspect ratio
    width, height = img.size
    aspect_ratio = width / height
    if not (MIN_ASPECT_RATIO <= aspect_ratio <= MAX_ASPECT_RATIO):
        raise ValueError(
            "Image must be reasonably square — no panoramas or skyscrapers."
        )

    # Resize image if necessary
    if width > MAX_WIDTH or height > MAX_HEIGHT:
        img.thumbnail((MAX_WIDTH, MAX_HEIGHT), Image.Resampling.LANCZOS)

    # Save to memory buffer
    buffer = BytesIO()
    img.save(buffer, format=img_format, quality=85, optimize=True)
    return ContentFile(buffer.getvalue())


def create_square_thumbnail(image, size):
    """
    Create a square thumbnail from an image by center-cropping then resizing.

    This ensures thumbnails are always square and properly sized for
    consistent display in member bubbles and lists.

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


def generate_profile_thumbnails(uploaded_file):
    """
    Generate all required profile photo sizes from an uploaded image.

    Creates three versions:
    - Original/Large: Max 800x800, maintains aspect ratio
    - Medium: 200x200 square thumbnail for profile views
    - Small: 64x64 square thumbnail for navbar/lists

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
        img_format = img.format or "JPEG"
        img = img.convert("RGB")
    except Exception as e:
        raise ValueError(f"Invalid image file: {e}")

    # Check aspect ratio
    width, height = img.size
    aspect_ratio = width / height
    if not (MIN_ASPECT_RATIO <= aspect_ratio <= MAX_ASPECT_RATIO):
        raise ValueError(
            "Image must be reasonably square — no panoramas or skyscrapers."
        )

    result = {}

    # Create original/large version (maintains aspect ratio)
    original = img.copy()
    if width > MAX_WIDTH or height > MAX_HEIGHT:
        original.thumbnail((MAX_WIDTH, MAX_HEIGHT), Image.Resampling.LANCZOS)

    buffer = BytesIO()
    original.save(buffer, format="JPEG", quality=85, optimize=True)
    result["original"] = ContentFile(buffer.getvalue())

    # Create medium thumbnail (square crop)
    medium = create_square_thumbnail(img, THUMBNAIL_MEDIUM)
    buffer = BytesIO()
    medium.save(buffer, format="JPEG", quality=85, optimize=True)
    result["medium"] = ContentFile(buffer.getvalue())

    # Create small thumbnail (square crop)
    small = create_square_thumbnail(img, THUMBNAIL_SMALL)
    buffer = BytesIO()
    small.save(buffer, format="JPEG", quality=85, optimize=True)
    result["small"] = ContentFile(buffer.getvalue())

    logger.info(
        f"Generated profile thumbnails: original={original.size}, "
        f"medium={THUMBNAIL_MEDIUM}x{THUMBNAIL_MEDIUM}, "
        f"small={THUMBNAIL_SMALL}x{THUMBNAIL_SMALL}"
    )

    return result


def generate_thumbnails_from_existing(image_path):
    """
    Generate thumbnails from an existing profile photo file.

    Used for backfilling thumbnails for members who already have photos.

    Args:
        image_path: Path to the existing image file

    Returns:
        dict with keys 'medium', 'small', each containing
        a ContentFile ready to be saved

    Raises:
        ValueError: If the image cannot be opened or processed
        FileNotFoundError: If the image file doesn't exist
    """
    try:
        with open(image_path, "rb") as f:
            img = Image.open(f)
            img.load()  # Force load before file closes
            img = img.convert("RGB")
    except FileNotFoundError:
        raise FileNotFoundError(f"Image file not found: {image_path}")
    except Exception as e:
        raise ValueError(f"Could not process image {image_path}: {e}")

    result = {}

    # Create medium thumbnail
    medium = create_square_thumbnail(img, THUMBNAIL_MEDIUM)
    buffer = BytesIO()
    medium.save(buffer, format="JPEG", quality=85, optimize=True)
    result["medium"] = ContentFile(buffer.getvalue())

    # Create small thumbnail
    small = create_square_thumbnail(img, THUMBNAIL_SMALL)
    buffer = BytesIO()
    small.save(buffer, format="JPEG", quality=85, optimize=True)
    result["small"] = ContentFile(buffer.getvalue())

    return result
