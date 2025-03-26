import os
import pydenticon
from django.conf import settings

def generate_identicon(username, relative_path):
    """Generate a unique identicon and save as a PNG image."""
    generator = pydenticon.Generator(
        5, 5,  # grid size
        foreground=["#1abc9c", "#2ecc71", "#3498db", "#9b59b6", "#34495e"],
        background="#ffffff"
    )

    full_path = os.path.join(settings.MEDIA_ROOT, relative_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)

    with open(full_path, "wb") as f:
        f.write(generator.generate(username, 250, 250, output_format="png"))
