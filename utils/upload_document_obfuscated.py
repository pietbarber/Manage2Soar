import os
import secrets


def upload_document_obfuscated(instance, filename):
    """
    Store restricted files under `cms/<page-slug>/<randomized-filename>`.

    The original file extension is preserved on the randomized filename.
    """
    page_slug = instance.page.slug if instance.page else "uncategorized"
    name, ext = os.path.splitext(filename)
    token = secrets.token_urlsafe(8)
    return f"cms/{page_slug}/{token}{ext}"
