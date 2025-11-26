# members/constants/membership.py
"""
Legacy membership-related constants for the project.

DEPRECATION NOTICE:
===================
These constants are DEPRECATED and will be removed in a future version.

Instead of using these constants directly, use the centralized helpers:

    from members.utils.membership import (
        get_active_membership_statuses,   # Replaces DEFAULT_ACTIVE_STATUSES
        get_all_membership_statuses,      # Replaces ALLOWED_MEMBERSHIP_STATUSES
    )

Membership statuses are now configured via the siteconfig.MembershipStatus model
in Django admin. This allows clubs to customize their membership status types
without code changes.

These constants remain only for migration fallback scenarios when the database
is not yet available. New code should NEVER import these directly.
"""

# =============================================================================
# DEPRECATED: Use members.utils.membership.get_all_membership_statuses() instead
# =============================================================================
ALLOWED_MEMBERSHIP_STATUSES = [
    "Charter Member",
    "Full Member",
    "Probationary Member",
    "Student Member",
    "Family Member",
    "Service Member",
    "Founding Member",
    "Honorary Member",
    "Emeritus Member",
    "SSEF Member",
    "Transient Member",
    "Temporary Member",
    "Introductory Member",
    "Inactive",
    "Non-Member",
    "Pending",
    "Role Account",
    "Deceased",
]

# =============================================================================
# DEPRECATED: Use members.utils.membership.get_active_membership_statuses() instead
# =============================================================================
DEFAULT_ACTIVE_STATUSES = [
    "Charter Member",
    "Full Member",
    "Probationary Member",
    "FAST Member",
    "Introductory Member",
    "Affiliate Member",
    "Family Member",
    "Service Member",
    "Student Member",
    "Transient Member",
    "Emeritus Member",
    "Honorary Member",
]

MEMBERSHIP_STATUS_CHOICES = [
    ("Charter Member", "Charter Member"),
    ("Full Member", "Full Member"),
    ("Probationary Member", "Probationary Member"),
    ("FAST Member", "FAST Member"),
    ("Introductory Member", "Introductory Member"),
    ("Affiliate Member", "Affiliate Member"),
    ("Family Member", "Family Member"),
    ("Service Member", "Service Member"),
    ("Student Member", "Student Member"),
    ("Transient Member", "Transient Member"),
    ("Emeritus Member", "Emeritus Member"),
    ("Honorary Member", "Honorary Member"),
    ("Inactive", "Inactive"),
    ("Non-Member", "Non-Member"),
    ("Pending", "Pending"),
    ("Role Account", "Role Account"),  # System/robot accounts
    ("Deceased", "Deceased"),
]

US_STATE_CHOICES = [
    ("AL", "Alabama"),
    ("AK", "Alaska"),
    ("AZ", "Arizona"),
    ("AR", "Arkansas"),
    ("CA", "California"),
    ("CO", "Colorado"),
    ("CT", "Connecticut"),
    ("DE", "Delaware"),
    ("FL", "Florida"),
    ("GA", "Georgia"),
    ("HI", "Hawaii"),
    ("ID", "Idaho"),
    ("IL", "Illinois"),
    ("IN", "Indiana"),
    ("IA", "Iowa"),
    ("KS", "Kansas"),
    ("KY", "Kentucky"),
    ("LA", "Louisiana"),
    ("ME", "Maine"),
    ("MD", "Maryland"),
    ("MA", "Massachusetts"),
    ("MI", "Michigan"),
    ("MN", "Minnesota"),
    ("MS", "Mississippi"),
    ("MO", "Missouri"),
    ("MT", "Montana"),
    ("NE", "Nebraska"),
    ("NV", "Nevada"),
    ("NH", "New Hampshire"),
    ("NJ", "New Jersey"),
    ("NM", "New Mexico"),
    ("NY", "New York"),
    ("NC", "North Carolina"),
    ("ND", "North Dakota"),
    ("OH", "Ohio"),
    ("OK", "Oklahoma"),
    ("OR", "Oregon"),
    ("PA", "Pennsylvania"),
    ("RI", "Rhode Island"),
    ("SC", "South Carolina"),
    ("SD", "South Dakota"),
    ("TN", "Tennessee"),
    ("TX", "Texas"),
    ("UT", "Utah"),
    ("VT", "Vermont"),
    ("VA", "Virginia"),
    ("WA", "Washington"),
    ("WV", "West Virginia"),
    ("WI", "Wisconsin"),
    ("WY", "Wyoming"),
]

STATUS_ALIASES = {
    "active": DEFAULT_ACTIVE_STATUSES,
    "inactive": ["Inactive"],
    "nonmember": ["Non-Member"],
    "pending": ["Pending"],
    "deceased": ["Deceased"],
}

DEFAULT_ROLES = [
    "instructor",
    "duty_officer",
    "assistant_duty_officer",
    "towpilot",
]

ROLE_FIELD_MAP = {
    "instructor": "instructor",
    "duty_officer": "duty_officer",
    "assistant_duty_officer": "assistant_duty_officer",
    "towpilot": "tow_pilot",
}
