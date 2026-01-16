import os
import re
import secrets

from django.utils.text import get_valid_filename


def upload_document_obfuscated(instance, filename):
    """
    Store restricted files under cms/<page-slug>/<filename-randomized> preserving extension.

    Note: uses os.path.splitext(), so only the last extension is preserved
    (e.g., archive.tar.gz becomes archive.tar-<token>.gz).
    Existing files uploaded with the old token-only naming remain unchanged.
    """
    page_slug = instance.page.slug if instance.page else "uncategorized"
    base_filename = os.path.basename(filename)
    name, ext = os.path.splitext(base_filename)
    ext = ext.strip()
    if ext:
        ext_name = get_valid_filename(ext.lstrip(".")) or ""
        ext_name = "".join(ch for ch in ext_name if ch.isalnum())
        if "script" in ext_name.lower():
            ext_name = ""
        ext = f".{ext_name}" if ext_name else ""
    else:
        ext = ""
    stripped_name = name.strip()
    if stripped_name in {"", ".", ".."}:
        safe_name = "file"
    else:
        safe_name = stripped_name.replace(" ", "_")
        # Intentionally strip dots and other non-word characters from the base filename.
        # This avoids extension confusion (e.g., "evil.php.txt" -> "evilphp-<token>.txt").
        # The actual extension is handled separately via os.path.splitext() and cleaned above.
        safe_name = re.sub(r"(?u)[^-\w]", "", safe_name)
        if safe_name in {"", ".", ".."}:
            safe_name = "file"
    if "script" in base_filename.lower():
        safe_name = "file"
    token = secrets.token_urlsafe(8)
    return f"cms/{page_slug}/{safe_name}-{token}{ext}"
