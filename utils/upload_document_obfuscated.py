import os
import secrets

from django.utils.text import get_valid_filename


def upload_document_obfuscated(instance, filename):
    """Store restricted files under cms/<page-slug>/<filename-randomized> preserving extension."""
    page_slug = instance.page.slug if instance.page else "uncategorized"
    base_filename = os.path.basename(filename)
    name, ext = os.path.splitext(base_filename)
    safe_name = get_valid_filename(name) or "file"
    token = secrets.token_urlsafe(8)
    return f"cms/{page_slug}/{safe_name}-{token}{ext}"
