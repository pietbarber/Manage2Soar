import logging
from io import BytesIO

from django.core.files.base import ContentFile
from PIL import Image, ImageOps

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
        # Apply EXIF orientation before any processing to handle rotated photos
        img = ImageOps.exif_transpose(img) or img
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
        # Apply EXIF orientation before any processing to handle rotated photos
        img = ImageOps.exif_transpose(img) or img
        # Always convert to RGB and save as JPEG for consistency
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
        f"Generated profile thumbnails: original={original.size}, "
        f"medium={THUMBNAIL_MEDIUM}x{THUMBNAIL_MEDIUM}, "
        f"small={THUMBNAIL_SMALL}x{THUMBNAIL_SMALL}"
    )

    return result
