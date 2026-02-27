"""
Username generation utilities for Member accounts.

The canonical username format is ``firstname.lastname`` (lower-case, letters
only).  When a collision occurs an incrementing numeric suffix is appended:
``john.smith``, ``john.smith1``, ``john.smith2``, …
"""

import re


def generate_username(first_name: str, last_name: str) -> str:
    """Return a unique ``firstname.lastname`` username.

    Strips all non-alphabetic characters from both name parts, combines them
    with a dot, and adds an incrementing suffix if the base username is already
    taken.

    Args:
        first_name: The member's first name (raw, may contain spaces/hyphens/etc.)
        last_name:  The member's last name.

    Returns:
        A unique username string that does not yet exist in the Member table.
    """
    # Import locally to avoid circular imports (members.utils is part of the
    # members app itself, so a top-level import of Member would be circular).
    from members.models import Member

    first_clean = re.sub(r"[^A-Za-z]", "", first_name).lower()
    last_clean = re.sub(r"[^A-Za-z]", "", last_name).lower()
    base_username = f"{first_clean}.{last_clean}"

    username = base_username
    counter = 1
    while Member.objects.filter(username=username).exists():
        username = f"{base_username}{counter}"
        counter += 1

    return username
