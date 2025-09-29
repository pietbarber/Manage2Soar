import pydenticon
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage


def generate_identicon(username, relative_path):
    """Generate a unique identicon and save as a PNG image using Django's storage backend."""
    generator = pydenticon.Generator(
        5, 5,  # grid size
        foreground=["#1abc9c", "#2ecc71", "#3498db", "#9b59b6", "#34495e"],
        background="#ffffff"
    )

    data = generator.generate(username, 250, 250, output_format="png")
    if isinstance(data, str):
        data = data.encode('utf-8')
    # Save using Django's default storage (works with GCP, S3, etc.)
    default_storage.save(relative_path, ContentFile(data))
