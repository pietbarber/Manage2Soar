import os

from django.conf import settings
from django.contrib.auth.models import AbstractUser, Group
from django.db import models, transaction
from tinymce.models import HTMLField

from members.constants.membership import MEMBERSHIP_STATUS_CHOICES, US_STATE_CHOICES
from utils.upload_entropy import (
    upload_badge_image,
    upload_biography,
    upload_profile_photo,
    upload_profile_photo_medium,
    upload_profile_photo_small,
)

# Membership application models are in models_applications.py to avoid circular imports
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
    # Thumbnail fields for efficient display in lists and navbars
    profile_photo_medium = models.ImageField(
        upload_to=upload_profile_photo_medium,
        blank=True,
        null=True,
        help_text="200x200 square thumbnail for profile views",
    )
    profile_photo_small = models.ImageField(
        upload_to=upload_profile_photo_small,
        blank=True,
        null=True,
        help_text="64x64 square thumbnail for navbar and lists",
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
    safety_officer = models.BooleanField(
        default=False,
        help_text="Safety Officer/Coach - receives safety reports from members",
    )

    joined_club = models.DateField(blank=True, null=True)
    emergency_contact = models.TextField(blank=True, null=True)
    home_club = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Home soaring club or organization for visiting pilots",
    )

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

    @property
    def profile_image_url_medium(self):
        """
        Return URL for medium (200x200) thumbnail.
        Falls back to full image if thumbnail not available, then pydenticon.
        """
        if self.profile_photo_medium:
            if hasattr(self.profile_photo_medium, "url"):
                return self.profile_photo_medium.url
            return f"{settings.MEDIA_URL}{self.profile_photo_medium}"
        # Fallback to full image
        return self.profile_image_url

    @property
    def profile_image_url_small(self):
        """
        Return URL for small (64x64) thumbnail.
        Falls back to medium, then full image, then pydenticon.
        """
        if self.profile_photo_small:
            if hasattr(self.profile_photo_small, "url"):
                return self.profile_photo_small.url
            return f"{settings.MEDIA_URL}{self.profile_photo_small}"
        # Fallback chain: medium -> full -> pydenticon
        if self.profile_photo_medium:
            return self.profile_image_url_medium
        return self.profile_image_url

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
    # Returns True if the member's membership_status is in the configured active statuses.
    # Active statuses are configured via siteconfig.MembershipStatus in Django admin.
    # Used for filtering members in operational roles and UI.

    def is_active_member(self):
        """Check if this member has an active membership status.

        Active statuses are determined by siteconfig.MembershipStatus model.
        This uses the centralized helper from members.utils.membership.

        Returns:
            bool: True if member's status is in active statuses list.
        """
        from .utils.membership import get_active_membership_statuses

        return self.membership_status in get_active_membership_statuses()

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
        if self.secretary:
            names.append("Secretary")
        if self.treasurer:
            names.append("Treasurer")
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
                # Grant staff status to instructors, member managers, rostermeisters, webmasters, secretaries, or treasurers
                self.is_staff = (
                    self.instructor
                    or self.member_manager
                    or self.rostermeister
                    or self.webmaster
                    or self.secretary
                    or self.treasurer
                )

        # 2) Sync is_active with membership status
        # Only activate Django User if member has an active membership status
        # This ensures login access is automatically managed based on membership status
        if not self.is_superuser:  # Don't override superuser active status
            self.is_active = self.is_active_member()

        # 3) avatar generation (safe pre-save)
        if not self.profile_photo:
            # Skip avatar generation in test environments to prevent storage pollution
            if not (hasattr(settings, "TESTING") and settings.TESTING):
                filename = f"profile_{self.username}.png"
                file_path = os.path.join("generated_avatars", filename)
                full_path = os.path.join("media", file_path)
                # Use try-except to avoid TOCTOU vulnerability
                try:
                    with open(full_path, "rb"):
                        pass  # File exists, do nothing
                except FileNotFoundError:
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
# - parent_badge: optional FK to the parent badge (for legs referencing full badge)

# Used in a many-to-many relationship with members through MemberBadge.


class Badge(models.Model):
    name = models.CharField(max_length=100, unique=True)
    image = models.ImageField(upload_to=upload_badge_image, blank=True, null=True)
    description = HTMLField(blank=True)
    order = models.PositiveIntegerField(default=0)
    parent_badge = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="legs",
        help_text="Parent badge (e.g., FAI Silver for Silver Duration leg). "
        "When a member has earned the parent, legs are hidden on the badge board.",
    )

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return self.name

    @property
    def is_leg(self):
        """Return True if this badge is a leg (has a parent badge)."""
        return self.parent_badge is not None


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


#########################
# KioskToken Model (Issue #364)
#
# Enables passwordless authentication for dedicated kiosk devices (e.g., club laptop).
# Uses a magic URL with device fingerprinting for security.
#
# Fields:
# - user: The role account this token authenticates as
# - token: Cryptographically secure token (used in magic URL)
# - name: Human-readable identifier (e.g., "Club Laptop")
# - device_fingerprint: Hash of device characteristics for binding
# - is_active: Can be revoked by admin
# - created_at/last_used_at: For auditing
# - landing_page: Where to redirect after authentication


class KioskToken(models.Model):
    """Token for passwordless kiosk device authentication."""

    LANDING_PAGE_CHOICES = [
        ("logsheet:today", "Today's Logsheet"),
        ("logsheet:index", "All Logsheets"),
        ("duty_roster:my_duties", "Duty Roster"),
        ("members:member_list", "Member List"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="kiosk_tokens",
        help_text="The role account this token authenticates as",
    )
    token = models.CharField(
        max_length=64,
        unique=True,
        editable=False,
        help_text="Cryptographic token for magic URL (auto-generated, 64 chars = ~288 bits entropy from secrets.token_urlsafe(48))",
    )
    name = models.CharField(
        max_length=100,
        help_text="Human-readable name (e.g., 'Club Laptop', 'Field Tablet')",
    )
    device_fingerprint = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        help_text="SHA-256 hash of device characteristics (set on first use)",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Uncheck to immediately revoke this token",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(blank=True, null=True)
    last_used_ip = models.GenericIPAddressField(blank=True, null=True)
    landing_page = models.CharField(
        max_length=50,
        choices=LANDING_PAGE_CHOICES,
        default="logsheet:index",
        help_text="Page to redirect to after authentication",
    )
    notes = models.TextField(
        blank=True,
        help_text="Admin notes about this token/device",
    )

    class Meta:
        verbose_name = "Kiosk Token"
        verbose_name_plural = "Kiosk Tokens"
        ordering = ["-created_at"]

    def __str__(self):
        status = "Active" if self.is_active else "Revoked"
        return f"{self.name} ({status})"

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = self._generate_token()
        super().save(*args, **kwargs)

    @staticmethod
    def _generate_token():
        """Generate a cryptographically secure token."""
        import secrets

        return secrets.token_urlsafe(48)

    def regenerate_token(self):
        """Generate a new token, invalidating the old URL."""
        self.token = self._generate_token()
        self.device_fingerprint = None  # Require re-binding
        self.save()
        return self.token

    def get_magic_url(self):
        """Return the magic URL for this token."""
        from django.urls import reverse

        return reverse("members:kiosk_login", kwargs={"token": self.token})

    def bind_device(self, fingerprint):
        """Bind this token to a specific device fingerprint."""
        self.device_fingerprint = fingerprint
        self.save(update_fields=["device_fingerprint"])

    def is_device_bound(self):
        """Check if token is bound to a device."""
        return bool(self.device_fingerprint)

    def should_allow_fingerprint(self, fingerprint):
        """
        Determine whether this token should be accepted for the given device
        fingerprint.

        Returns True if:
        - the token is not yet bound (first use; caller may bind the device), or
        - the stored fingerprint matches the provided fingerprint.
        """
        if not self.device_fingerprint:
            return True  # Not yet bound, will be bound on this request
        return self.device_fingerprint == fingerprint

    def validate_fingerprint(self, fingerprint):
        """
        Backwards-compatible wrapper for should_allow_fingerprint().

        This method historically both validated fingerprints for already-bound
        devices and allowed the first binding when no fingerprint was stored.
        New code should prefer should_allow_fingerprint() for clarity.

        DEPRECATED: Use should_allow_fingerprint() instead for clearer semantics.
        This method will be maintained for backwards compatibility but may be
        removed in a future major version.
        """
        return self.should_allow_fingerprint(fingerprint)

    def record_usage(self, ip_address=None):
        """Record that this token was used."""
        from django.utils import timezone

        self.last_used_at = timezone.now()
        if ip_address:
            self.last_used_ip = ip_address
        self.save(update_fields=["last_used_at", "last_used_ip"])


class KioskAccessLog(models.Model):
    """Audit log for kiosk token access attempts."""

    STATUS_CHOICES = [
        ("success", "Success"),
        ("invalid_token", "Invalid Token"),
        ("inactive_token", "Inactive Token"),
        ("fingerprint_mismatch", "Fingerprint Mismatch"),
        ("bound", "Device Bound"),
    ]

    kiosk_token = models.ForeignKey(
        KioskToken,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="access_logs",
    )
    token_value = models.CharField(
        max_length=64,
        help_text="Token value attempted (for failed lookups)",
    )
    timestamp = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.TextField(blank=True)
    device_fingerprint = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    details = models.TextField(blank=True)

    class Meta:
        verbose_name = "Kiosk Access Log"
        verbose_name_plural = "Kiosk Access Logs"
        ordering = ["-timestamp"]

    def __str__(self):
        return f"{self.timestamp} - {self.status}"


#########################
# SafetyReport Model
#
# Stores safety-related observations reported by members.
# Supports anonymous reporting to encourage honest safety feedback.
# Safety officers can review and manage reports.
#
# Related: Issue #554 - Add Safety Report form accessible to any member


class SafetyReport(models.Model):
    """Safety observation report submitted by club members.

    Members can report safety-related observations anonymously or with
    their identity attached. Reports are visible to safety officers
    for review and to facilitate club safety meetings.
    """

    STATUS_CHOICES = [
        ("new", "New"),
        ("reviewed", "Reviewed"),
        ("in_progress", "In Progress"),
        ("resolved", "Resolved"),
        ("closed", "Closed"),
    ]

    # Who submitted the report (null if anonymous)
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="safety_reports_submitted",
        help_text="Member who submitted the report (null if anonymous)",
    )

    # Flag to indicate if report was submitted anonymously
    is_anonymous = models.BooleanField(
        default=False,
        help_text="If true, reporter identity is hidden from all viewers",
    )

    # The report content - rich text for detailed descriptions
    observation = HTMLField(
        help_text="What did you observe? Describe the safety concern in detail.",
    )

    # Optional: Date when the observation occurred
    observation_date = models.DateField(
        blank=True,
        null=True,
        help_text="Date when the observation occurred (optional)",
    )

    # Optional: Location where observation occurred
    location = models.CharField(
        max_length=200,
        blank=True,
        help_text="Location where the observation occurred (optional)",
    )

    # Tracking fields
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="new",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Safety officer who reviewed the report
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="safety_reports_reviewed",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    # Safety officer notes (not visible to reporter)
    officer_notes = HTMLField(
        blank=True,
        null=True,
        help_text="Internal notes for safety officers (not visible to reporter)",
    )

    # Optional follow-up actions taken
    actions_taken = HTMLField(
        blank=True,
        null=True,
        help_text="Description of actions taken to address the concern",
    )

    class Meta:
        verbose_name = "Safety Report"
        verbose_name_plural = "Safety Reports"
        ordering = ["-created_at"]

    def __str__(self):
        if self.is_anonymous:
            reporter_name = "Anonymous"
        elif self.reporter:
            reporter_name = self.reporter.get_full_name() or self.reporter.username
        else:
            reporter_name = "Unknown"
        return f"Safety Report #{self.pk} by {reporter_name} ({self.created_at.strftime('%Y-%m-%d')})"

    def get_reporter_display(self):
        """Return display name for reporter, respecting anonymity."""
        if self.is_anonymous:
            return "Anonymous"
        if self.reporter:
            return self.reporter.get_full_name() or self.reporter.username
        return "Unknown"


# Import MembershipApplication model from separate file to keep models.py manageable
