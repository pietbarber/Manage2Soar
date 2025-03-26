from PIL import Image
from io import BytesIO
from django.core.files.base import ContentFile

# Configurable settings
MAX_WIDTH = 800
MAX_HEIGHT = 800
MIN_ASPECT_RATIO = 0.5   # Tallest allowed is 2:1 (portrait)
MAX_ASPECT_RATIO = 2.0   # Widest allowed is 2:1 (landscape)

def resize_and_crop_profile_photo(uploaded_file):
    """
    Resizes and checks aspect ratio of uploaded profile photo.
    Returns a ContentFile ready to be saved, or raises ValueError.
    """
    try:
        img = Image.open(uploaded_file)
        img_format = img.format or 'JPEG'  # Default to JPEG if format missing
        img = img.convert('RGB')  # Always save in RGB for JPEG/PNG safety
    except Exception as e:
        raise ValueError(f"Invalid image file: {e}")

    # Check aspect ratio
    width, height = img.size
    aspect_ratio = width / height
    if not (MIN_ASPECT_RATIO <= aspect_ratio <= MAX_ASPECT_RATIO):
        raise ValueError("Image must be reasonably square — no panoramas or skyscrapers.")

    # Resize image if necessary
    if width > MAX_WIDTH or height > MAX_HEIGHT:
        img.thumbnail((MAX_WIDTH, MAX_HEIGHT), Image.Resampling.LANCZOS)

    # Save to memory buffer
    buffer = BytesIO()
    img.save(buffer, format=img_format, quality=85, optimize=True)
    return ContentFile(buffer.getvalue())
