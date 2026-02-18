from PIL import Image

# Filename under MEDIA_ROOT used for the club-branded PWA / Apple touch icon.
PWA_CLUB_ICON_NAME = "pwa-icon-club.png"


def generate_favicon_from_logo(input_file, output_file):
    """
    Convert the uploaded logo to a favicon.ico file with standard sizes.
    input_file: file-like object (rb mode)
    output_file: file-like object (wb mode or BytesIO)
    """
    sizes = [(16, 16), (32, 32), (48, 48)]
    img = Image.open(input_file)
    img = img.convert("RGBA")  # Ensure transparency is preserved if present
    icons = [img.resize(size, Image.LANCZOS) for size in sizes]
    icons[0].save(output_file, format="ICO", sizes=sizes)


def generate_pwa_icon_from_logo(input_file, output_file, size=192):
    """
    Resize the uploaded club logo to a square PNG suitable for use as a PWA
    icon and Apple touch icon (default 192×192).

    input_file:  file-like object opened in binary read mode.
    output_file: file-like object opened in binary write mode (or BytesIO).
    size:        side length in pixels for the square output image.
    """
    img = Image.open(input_file)
    img = img.convert("RGBA")  # preserve transparency
    img = img.resize((size, size), Image.LANCZOS)
    img.save(output_file, format="PNG")
