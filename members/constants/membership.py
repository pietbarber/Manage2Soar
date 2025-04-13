# members/constants/membership.py

ALLOWED_MEMBERSHIP_STATUSES = [
    "Full Member",
    "Student Member",
    "Family Member",
    "Service Member",
    "Founding Member",
    "Honorary Member",
    "Emeritus Member",
    "SSEF Member",
    "Temporary Member",
    "Introductory Member",
]

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
    ('Inactive', 'Inactive'),
    ('Non-Member', 'Non-Member'),
    ('Pending', 'Pending'),
    ('Deceased', 'Deceased'),
]

US_STATE_CHOICES = [
    ('AL', 'Alabama'), ('AK', 'Alaska'), ('AZ', 'Arizona'), ('AR', 'Arkansas'),
    ('CA', 'California'), ('CO', 'Colorado'), ('CT', 'Connecticut'), ('DE', 'Delaware'),
    ('FL', 'Florida'), ('GA', 'Georgia'), ('HI', 'Hawaii'), ('ID', 'Idaho'),
    ('IL', 'Illinois'), ('IN', 'Indiana'), ('IA', 'Iowa'), ('KS', 'Kansas'),
    ('KY', 'Kentucky'), ('LA', 'Louisiana'), ('ME', 'Maine'), ('MD', 'Maryland'),
    ('MA', 'Massachusetts'), ('MI', 'Michigan'), ('MN', 'Minnesota'), ('MS', 'Mississippi'),
    ('MO', 'Missouri'), ('MT', 'Montana'), ('NE', 'Nebraska'), ('NV', 'Nevada'),
    ('NH', 'New Hampshire'), ('NJ', 'New Jersey'), ('NM', 'New Mexico'), ('NY', 'New York'),
    ('NC', 'North Carolina'), ('ND', 'North Dakota'), ('OH', 'Ohio'), ('OK', 'Oklahoma'),
    ('OR', 'Oregon'), ('PA', 'Pennsylvania'), ('RI', 'Rhode Island'), ('SC', 'South Carolina'),
    ('SD', 'South Dakota'), ('TN', 'Tennessee'), ('TX', 'Texas'), ('UT', 'Utah'),
    ('VT', 'Vermont'), ('VA', 'Virginia'), ('WA', 'Washington'), ('WV', 'West Virginia'),
    ('WI', 'Wisconsin'), ('WY', 'Wyoming')
]

STATUS_ALIASES = {
    "active": DEFAULT_ACTIVE_STATUSES,
    "inactive": ["Inactive"],
    "nonmember": ["Non-Member"],
    "pending": ["Pending"],
    "deceased": ["Deceased"],
}