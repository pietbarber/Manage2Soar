import os

from django.conf import settings
from django.contrib.auth.models import AbstractUser, Group
from django.db import models, transaction
from tinymce.models import HTMLField

from members.constants.membership import (
    DEFAULT_ACTIVE_STATUSES,
    MEMBERSHIP_STATUS_CHOICES,
    US_STATE_CHOICES,
)
from utils.upload_entropy import (
    upload_badge_image,
    upload_biography,
    upload_profile_photo,
)

from .utils.avatar_generator import generate_identicon


def get_membership_status_choices():
    """
    Get membership status choices dynamically from the MembershipStatus model.
    Falls back to hardcoded choices during migrations or if MembershipStatus doesn't exist.
    """
    try:
        from siteconfig.models import MembershipStatus
        return MembershipStatus.get_all_status_choices()
    except (ImportError, Exception):
        # Fallback to hardcoded choices during migrations or if table doesn't exist
        return MEMBERSHIP_STATUS_CHOICES


def biography_upload_path(instance, filename):
    return f"biography/{instance.member.username}/{filename}"


class Biography(models.Model):
    member = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    content = HTMLField(blank=True, null=True)
    uploaded_image = models.ImageField(
        upload_to=upload_biography, blank=True, null=True
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Biographies"

    def __str__(self):
        return f"Biography of {self.member.get_full_name()}"


#########################
# Member Model

# Extends Django's AbstractUser to represent a club member.
# Includes personal information, contact details, SSA membership info,
# club roles, and membership status.

# Fields:
# - middle_initial: optional middle initial
# - name_suffix: suffix (Jr., Sr., III, etc.)
# - nickname: alternate first name or call sign
# - phone / mobile_phone: contact numbers
# - emergency_contact: emergency contact info
# - address, city, state_code/state_freeform, zip_code, country: mailing address
# - membership_status: current member status (active, student, etc.)
# - SSA_member_number: Soaring Society of America ID
# - glider_rating: pilot certification level (student, private, commercial)
# - public_notes: viewable by all logged-in users
# - private_notes: visible only to officers/managers
# - profile_photo: optional image used in member directory
# - instructor / towpilot / duty_officer / assistant_duty_officer: role booleans
# - director / treasurer / secretary / webmaster / member_manager: club management roles
# - legacy_username: preserved for linking imported data
# - date_joined: original join date
# - last_updated_by: tracks last editor of this record
# - badges: M2M relation to awarded badges
# - biography: optional related biography object

# Methods:
# - is_active_member(): Returns True if the member has a qualifying active membership status


class Member(AbstractUser):
    pilot_certificate_number = models.CharField(
        max_length=32,
        blank=True,
        null=True,
        help_text="FAA pilot certificate number (optional, but required for instructors giving instruction)",
    )
    private_glider_checkride_date = models.DateField(
        blank=True,
        null=True,
        help_text="Date member passed practical checkride for Private Pilot Glider.",
    )
    # Here are the legacy codes from the old database,
    # Legacy status codes:
    # M = Full Member
    # U = Student Member
    # Q = Family Member
    # F = Founding Member
    # H = Honorary Member
    # E = Introductory Member
    # C = SSEF Member (Scholarship)
    # I = Inactive
    # N = Non-Member
    # P = Probationary Member
    # T = Transient Member
    # A = FAST Member
    # S = Service Member

    membership_status = models.CharField(
        max_length=50,  # Increased length to accommodate longer status names
        choices=MEMBERSHIP_STATUS_CHOICES,  # Fallback for migrations
        default="Non-Member",
        blank=True,
        null=True,
    )

    NAME_SUFFIX_CHOICES = [
        ("", "—"),  # blank default
        ("Jr.", "Jr."),
        ("Sr.", "Sr."),
        ("II", "II"),
        ("III", "III"),
        ("IV", "IV"),
        ("V", "V"),
    ]

    # Additional name-related fields
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="member_profile",
        null=True,
        blank=True,
    )
    middle_initial = models.CharField(max_length=2, blank=True, null=True)
    nickname = models.CharField(max_length=50, blank=True, null=True)
    name_suffix = models.CharField(
        max_length=10,
        choices=NAME_SUFFIX_CHOICES,
        blank=True,
        null=True,
    )

    # Additional contact information fields

    SSA_member_number = models.CharField(
        max_length=20, unique=True, blank=True, null=True
    )
    ssa_url = models.URLField(
        max_length=300,
        blank=True,
        null=True,
        help_text="Direct link to this member's SSA page for badges and achievements.",
    )
    legacy_username = models.CharField(
        max_length=50, unique=True, blank=True, null=True
    )
    phone = models.CharField(max_length=20, blank=True, null=True)
    mobile_phone = models.CharField(max_length=20, blank=True, null=True)
    country = models.CharField(max_length=2, blank=True, null=True, default="US")
    address = models.TextField(blank=True, null=True)
    city = models.CharField(max_length=50, blank=True, null=True)
    state_code = models.CharField(
        max_length=2, choices=US_STATE_CHOICES, blank=True, null=True
    )
    state_freeform = models.CharField(max_length=50, blank=True, null=True)
    zip_code = models.CharField(max_length=10, blank=True, null=True)
    profile_photo = models.ImageField(
        upload_to=upload_profile_photo, blank=True, null=True
    )
    GLIDER_RATING_CHOICES = [
        ("none", "None"),
        ("student", "Student"),
        ("transition", "Transition"),
        ("private", "Private"),
        ("commercial", "Commercial"),
    ]
    glider_rating = models.CharField(
        max_length=10, choices=GLIDER_RATING_CHOICES, default="student"
    )

    instructor = models.BooleanField(default=False)
    towpilot = models.BooleanField(default=False)
    duty_officer = models.BooleanField(default=False)
    assistant_duty_officer = models.BooleanField(default=False)
    secretary = models.BooleanField(default=False)
    treasurer = models.BooleanField(default=False)
    webmaster = models.BooleanField(default=False)
    director = models.BooleanField(default=False)
    member_manager = models.BooleanField(default=False)
    rostermeister = models.BooleanField(default=False)

    joined_club = models.DateField(blank=True, null=True)
    emergency_contact = models.TextField(blank=True, null=True)

    public_notes = HTMLField(blank=True, null=True)
    private_notes = HTMLField(blank=True, null=True)

    last_updated_by = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True
    )
    # When True, personal contact details are hidden from non-privileged viewers
    redact_contact = models.BooleanField(
        default=False,
        help_text="If set, personal contact details (address, phones, email, QR) are hidden from non-privileged viewers.",
    )

    @property
    def profile_image_url(self):
        from django.urls import reverse

        if self.profile_photo:
            # If it's a FieldFile, it has .url; if it's a str, build a URL
            if hasattr(self.profile_photo, "url"):
                return self.profile_photo.url  # type: ignore[attr-defined]
            # Fallback for string paths
            return f"{settings.MEDIA_URL}{self.profile_photo}"
        return reverse("pydenticon", kwargs={"username": self.username})

    ##################################
    # full_display_name
    #
    # Return the member's display name for UI usage.
    # If a nickname exists, use it in place of the first name.
    # Example: 'Sam Gilbert' instead of 'Bret "Sam" Gilbert'
    #
    @property
    def full_display_name(self):
        if self.nickname:
            first = f"{self.nickname}"
        else:
            first = self.first_name

        name = f"{first} {self.middle_initial or ''} {self.last_name}".strip()

        if self.name_suffix:
            name = f"{name}, {self.name_suffix}"
        if self.membership_status == "Deceased":
            name += "†"
        return " ".join(name.split())  # Normalize spaces

    #################
    # is_active_member(self)
    # Returns True if the member's membership_status is in DEFAULT_ACTIVE_STATUSES.
    # Used for filtering members in operational roles and UI.

    def is_active_member(self):
        try:
            from siteconfig.models import MembershipStatus
            active_statuses = list(MembershipStatus.get_active_statuses())
            return self.membership_status in active_statuses
        except (ImportError, Exception):
            # Fallback to hardcoded list during migrations or if table doesn't exist
            return self.membership_status in DEFAULT_ACTIVE_STATUSES

    def _desired_group_names(self):
        names = []
        if self.rostermeister:
            names.append("Rostermeisters")
        if self.instructor:
            names.append("Instructor Admins")
        if self.member_manager:
            names.append("Member Managers")
        if self.webmaster:
            names.append("Webmasters")
        return names

    def _sync_groups(self):
        # Only safe after PK exists
        if not self.pk:
            return
        desired = []
        for name in self._desired_group_names():
            grp, _ = Group.objects.get_or_create(name=name)
            desired.append(grp)
        # Atomic replace; avoids add/remove churn
        self.groups.set(desired)

    @classmethod
    def get_membership_status_choices(cls):
        """Get dynamic membership status choices for forms."""
        try:
            from siteconfig.models import MembershipStatus
            return MembershipStatus.get_all_status_choices()
        except (ImportError, Exception):
            # Fallback during migrations or if table doesn't exist
            return MEMBERSHIP_STATUS_CHOICES

    def save(self, *args, **kwargs):
        # 1) pre-save flags
        # Always allow superusers to access admin
        if self.is_superuser:
            self.is_staff = True
        else:
            # If is_staff has been explicitly set (for example in tests via
            # create_user(is_staff=True)), preserve that explicit value. Only
            # auto-derive is_staff when it is currently False.
            if not self.is_staff:
                # Grant staff status to instructors, member managers, rostermeisters, or webmasters
                self.is_staff = (
                    self.instructor
                    or self.member_manager
                    or self.rostermeister
                    or self.webmaster
                )

        # 2) Sync is_active with membership status
        # Only activate Django User if member has an active membership status
        # This ensures login access is automatically managed based on membership status
        if not self.is_superuser:  # Don't override superuser active status
            self.is_active = self.is_active_member()

        # 3) avatar generation (safe pre-save)
        if not self.profile_photo:
            # Skip avatar generation in test environments to prevent storage pollution
            if not (hasattr(settings, 'TESTING') and settings.TESTING):
                filename = f"profile_{self.username}.png"
                file_path = os.path.join("generated_avatars", filename)
                if not os.path.exists(os.path.join("media", file_path)):
                    generate_identicon(self.username, file_path)
                self.profile_photo = file_path

        # 4) persist first – get a PK
        super().save(*args, **kwargs)

        # 5) now safe to touch M2M
        transaction.on_commit(self._sync_groups)

    ##################################
    #  def __str__
    # Returns a readable name for the member, (the full display name)
    # Used in admin dropdowns and member selectors.

    def __str__(self):
        return self.full_display_name


#########################
# Badge Model

# Defines all possible badges that can be earned by members, such as SSA badges (A, B, C, etc.)
# or club-specific awards.

# Fields:
# - name: full name of the badge (e.g., "SSA A Badge")
# - code: short identifier (e.g., "A")
# - description: text explanation of the badge
# - category: optional grouping for organizational purposes

# Used in a many-to-many relationship with members through MemberBadge.


class Badge(models.Model):
    name = models.CharField(max_length=100, unique=True)
    image = models.ImageField(upload_to=upload_badge_image, blank=True, null=True)
    description = HTMLField(blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return self.name


#########################
# MemberBadge Model

# Links a Member to a Badge. Represents a badge that has been earned.

# Fields:
# - member: foreign key to the Member who earned the badge
# - badge: the badge awarded
# - date_awarded: optional date of award
# - notes: optional comment for internal use


class MemberBadge(models.Model):
    member = models.ForeignKey(
        "Member", on_delete=models.CASCADE, related_name="badges"
    )
    badge = models.ForeignKey(Badge, on_delete=models.CASCADE)
    date_awarded = models.DateField()
    notes = models.TextField(blank=True)

    class Meta:
        unique_together = ("member", "badge")

    def __str__(self):
        return f"{self.member} - {self.badge.name}"
