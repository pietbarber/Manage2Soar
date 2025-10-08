from PIL import Image


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
    icons[0].save(output_file, format='ICO', sizes=sizes)
