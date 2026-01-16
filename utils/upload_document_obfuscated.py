import os
import re
import secrets


def upload_document_obfuscated(instance, filename):
    """
    Store restricted files under cms/<page-slug>/<filename-randomized> preserving extension.

    Platform notes:
    - Assumes Unix-style path handling. On Linux, backslashes in Windows-style paths
      (e.g., "C:\\evil\\file.pdf") are treated as regular characters and will be
      sanitized out by the regex, not as path separators.
    - Unicode letters/digits are allowed in filenames via the (?u) regex flag,
      supporting international characters (e.g., "文档.pdf" -> "文档-<token>.pdf").
    - Page slugs are assumed to be safe (Django's SlugField enforces this).

    Note: uses os.path.splitext(), so only the last extension is preserved
    (e.g., archive.tar.gz becomes archive.tar-<token>.gz).
    Existing files uploaded with the old token-only naming remain unchanged.
    """
    page_slug = instance.page.slug if instance.page else "uncategorized"
    base_filename = os.path.basename(filename)
    name, ext = os.path.splitext(base_filename)
    ext = ext.strip()
    if ext and "script" not in ext.lower():
        ext_name = re.sub(r"[^A-Za-z0-9]", "", ext.lstrip("."))
        ext = f".{ext_name}" if ext_name else ""
    else:
        ext = ""
    stripped_name = name.strip()
    if stripped_name in {"", ".", ".."}:
        safe_name = "file"
    else:
        # Convert spaces to underscores first so they survive the sanitization step
        # (the regex `(?u)[^-\w]` keeps underscores since \w includes them).
        safe_name = stripped_name.replace(" ", "_")
        # Intentionally strip dots and other non-word characters from the base filename.
        # This avoids extension confusion (e.g., "evil.php.txt" -> "evilphp-<token>.txt").
        # The actual extension is handled separately via os.path.splitext() and cleaned above.
        # The (?u) flag enables Unicode support, allowing international characters in filenames.
        safe_name = re.sub(r"(?u)[^-\w]", "", safe_name)
        if not safe_name:
            safe_name = "file"
    if "script" in base_filename.lower():
        safe_name = "file"
    token = secrets.token_urlsafe(8)
    return f"cms/{page_slug}/{safe_name}-{token}{ext}"
