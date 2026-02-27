"""
Username generation utilities for Member accounts.

The canonical username format is ``firstname.lastname`` (lower-case, letters
only).  When a collision occurs an incrementing numeric suffix is appended:
``john.smith``, ``john.smith1``, ``john.smith2``, …
"""

import re


def generate_username(first_name: str, last_name: str) -> str:
    """Return a unique ``firstname.lastname`` username.

    Strips all non-ASCII-alphabetic characters from both name parts (the regex
    ``[^A-Za-z]`` removes anything that is not an ASCII letter, including
    accented characters such as "é" or "Ö"), lowercases each part, and
    combines them with a dot.  An incrementing numeric suffix is appended if
    the base username is already taken.

    Args:
        first_name: The member's first name (raw, may contain spaces/hyphens/etc.)
        last_name:  The member's last name.

    Returns:
        A unique username string that does not yet exist in the Member table
        at the time of the check.  Note: the availability check and the
        subsequent ``create_user()`` call in the caller are not atomic; in
        a concurrent environment callers should catch ``IntegrityError`` and
        retry to handle the rare race condition.
    """
    # Import locally to avoid circular imports (members.utils is part of the
    # members app itself, so a top-level import of Member would be circular).
    from members.models import Member

    first_clean = re.sub(r"[^A-Za-z]", "", first_name).lower()
    last_clean = re.sub(r"[^A-Za-z]", "", last_name).lower()

    # Fall back gracefully when name parts contain no ASCII letters (e.g.
    # non-ASCII names like "李" or accented-only strings like "Ö").
    if not first_clean and not last_clean:
        base_username = "user"
    elif not first_clean:
        base_username = last_clean
    elif not last_clean:
        base_username = first_clean
    else:
        base_username = f"{first_clean}.{last_clean}"

    # Truncate to the model field's max_length, reserving space for a
    # numeric suffix so the final username always fits in the column.
    username_field = Member._meta.get_field("username")
    max_length = getattr(username_field, "max_length", 150)
    base_username = base_username[:max_length]

    username = base_username
    counter = 1
    while Member.objects.filter(username=username).exists():
        suffix = str(counter)
        truncated_base = base_username[: max_length - len(suffix)]
        username = f"{truncated_base}{suffix}"
        counter += 1

    return username
