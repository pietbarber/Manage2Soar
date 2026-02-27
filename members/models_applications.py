import uuid

from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone
from tinymce.models import HTMLField

from siteconfig.models import SiteConfiguration


class MembershipApplication(models.Model):
    """
    Model for membership applications from non-members who want to join the club.
    This is separate from the Member model since applicants are not yet members.
    """

    # Status choices for the application
    STATUS_CHOICES = [
        ("pending", "Pending Review"),
        ("under_review", "Under Review"),
        ("additional_info_needed", "Additional Information Needed"),
        ("approved", "Approved"),
        ("waitlisted", "On Waiting List"),
        ("rejected", "Rejected"),
        ("withdrawn", "Withdrawn"),
    ]

    # Unique identifier
    application_id = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        help_text="Unique identifier for this application",
    )

    # Basic application metadata
    status = models.CharField(
        max_length=25,
        choices=STATUS_CHOICES,
        default="pending",
        help_text="Current status of the application",
    )
    submitted_at = models.DateTimeField(
        default=timezone.now, help_text="When the application was originally submitted"
    )
    last_updated = models.DateTimeField(
        auto_now=True, help_text="When the application was last modified"
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_applications",
        help_text="Member manager who reviewed this application",
    )
    reviewed_at = models.DateTimeField(
        null=True, blank=True, help_text="When the application was reviewed"
    )

    # Personal Information (from PDF form section 1)
    first_name = models.CharField(max_length=150, help_text="First name")
    middle_initial = models.CharField(
        max_length=2, blank=True, help_text="Middle initial"
    )
    last_name = models.CharField(max_length=150, help_text="Last name")
    name_suffix = models.CharField(
        max_length=10,
        blank=True,
        choices=[
            ("", "—"),
            ("Jr.", "Jr."),
            ("Sr.", "Sr."),
            ("II", "II"),
            ("III", "III"),
            ("IV", "IV"),
            ("V", "V"),
        ],
        help_text="Name suffix",
    )

    # Contact information
    email = models.EmailField(help_text="Email address")
    phone = models.CharField(
        max_length=20,
        validators=[
            RegexValidator(
                regex=r"^\+?[\d\s\-\(\)\.]+$", message="Enter a valid phone number"
            )
        ],
        help_text="Phone number",
    )
    mobile_phone = models.CharField(
        max_length=20,
        blank=True,
        validators=[
            RegexValidator(
                regex=r"^\+?[\d\s\-\(\)\.]+$", message="Enter a valid phone number"
            )
        ],
        help_text="Mobile phone number (optional)",
    )

    # Address information
    address_line1 = models.CharField(max_length=200, help_text="Street address")
    address_line2 = models.CharField(
        max_length=200, blank=True, help_text="Apartment, suite, etc. (optional)"
    )
    city = models.CharField(max_length=100, help_text="City")
    state = models.CharField(max_length=100, help_text="State/Province")
    zip_code = models.CharField(max_length=20, help_text="ZIP/Postal code")
    country = models.CharField(max_length=100, default="USA", help_text="Country")

    # Emergency contact
    emergency_contact_name = models.CharField(
        max_length=200, help_text="Emergency contact full name"
    )
    emergency_contact_relationship = models.CharField(
        max_length=100, help_text="Relationship to applicant"
    )
    emergency_contact_phone = models.CharField(
        max_length=20,
        validators=[
            RegexValidator(
                regex=r"^\+?[\d\s\-\(\)\.]+$", message="Enter a valid phone number"
            )
        ],
        help_text="Emergency contact phone number",
    )

    # Aviation Experience (from PDF form section 2)
    pilot_certificate_number = models.CharField(
        max_length=32,
        blank=True,
        help_text="FAA pilot certificate number (if applicable)",
    )

    # Pilot ratings
    has_private_pilot = models.BooleanField(
        default=False, help_text="Private Pilot Certificate"
    )
    has_instrument_rating = models.BooleanField(
        default=False, help_text="Instrument Rating"
    )
    has_commercial_pilot = models.BooleanField(
        default=False, help_text="Commercial Pilot Certificate"
    )
    has_cfi = models.BooleanField(
        default=False, help_text="Certified Flight Instructor"
    )
    has_cfii = models.BooleanField(
        default=False, help_text="Certified Flight Instructor - Instrument"
    )

    # Glider-specific ratings
    GLIDER_RATING_CHOICES = [
        ("none", "None"),
        ("student", "Student"),
        ("transition", "Transition"),
        ("private", "Private Glider"),
        ("commercial", "Commercial Glider"),
        ("foreign", "Foreign Pilot"),
    ]
    glider_rating = models.CharField(
        max_length=15,
        choices=GLIDER_RATING_CHOICES,
        default="none",
        help_text="Current glider rating",
    )

    # Flight experience
    total_flight_hours = models.PositiveIntegerField(
        default=0, help_text="Total flight hours (all aircraft)"
    )
    glider_flight_hours = models.PositiveIntegerField(
        default=0, help_text="Total glider flight hours"
    )
    recent_flight_hours = models.PositiveIntegerField(
        default=0, help_text="Flight hours in the last 24 months"
    )

    # SSA Information
    ssa_member_number = models.CharField(
        max_length=20,
        blank=True,
        help_text="Soaring Society of America member number (if applicable)",
    )

    # Insurance/Club History (from PDF form section 3)
    previous_club_memberships = models.TextField(
        blank=True, help_text="List any previous soaring club memberships"
    )

    # Previous membership at THIS club
    previous_member_at_this_club = models.BooleanField(
        default=False, help_text="Have you ever been a member of this club before?"
    )
    previous_membership_details = models.TextField(
        blank=True,
        help_text="If yes, please provide details (approximate years, membership status when you left, etc.)",
    )

    insurance_rejection_history = models.BooleanField(
        default=False, help_text="Have you ever been rejected for aviation insurance?"
    )
    insurance_rejection_details = models.TextField(
        blank=True, help_text="If yes, please explain the circumstances"
    )

    club_rejection_history = models.BooleanField(
        default=False, help_text="Have you ever been rejected for club membership?"
    )
    club_rejection_details = models.TextField(
        blank=True, help_text="If yes, please explain the circumstances"
    )

    aviation_incidents = models.BooleanField(
        default=False,
        help_text="Have you been involved in any aviation incidents or accidents?",
    )
    aviation_incident_details = models.TextField(
        blank=True, help_text="If yes, please provide details"
    )

    # Goals and Interests
    soaring_goals = models.TextField(
        help_text="What are your goals with soaring? What interests you about our club?"
    )

    availability = models.TextField(
        blank=True,
        help_text="When are you typically available for club activities? (days, times, seasons)",
    )

    # References
    reference1_name = models.CharField(
        max_length=200, blank=True, help_text="Reference #1 name"
    )
    reference1_phone = models.CharField(
        max_length=20, blank=True, help_text="Reference #1 phone"
    )
    reference1_relationship = models.CharField(
        max_length=100, blank=True, help_text="Relationship to reference #1"
    )

    reference2_name = models.CharField(
        max_length=200, blank=True, help_text="Reference #2 name"
    )
    reference2_phone = models.CharField(
        max_length=20, blank=True, help_text="Reference #2 phone"
    )
    reference2_relationship = models.CharField(
        max_length=100, blank=True, help_text="Relationship to reference #2"
    )

    # Agreement/Terms (from PDF form section 4)
    agrees_to_terms = models.BooleanField(
        default=False, help_text="Applicant agrees to club terms and conditions"
    )
    agrees_to_safety_rules = models.BooleanField(
        default=False, help_text="Applicant agrees to follow all club safety rules"
    )
    agrees_to_financial_obligations = models.BooleanField(
        default=False, help_text="Applicant agrees to meet financial obligations"
    )

    # Additional notes from applicant
    additional_comments = models.TextField(
        blank=True,
        help_text="Any additional comments or information from the applicant",
    )

    # Administrative notes (for membership managers)
    admin_notes = HTMLField(
        blank=True,
        help_text="Private notes for membership managers (not visible to applicant)",
    )

    # Waitlist management
    waitlist_position = models.PositiveIntegerField(
        null=True, blank=True, help_text="Position on the waiting list (if applicable)"
    )

    # When approved, link to the created member account
    member_account = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="membership_application",
        help_text="Member account created when application was approved",
    )

    class Meta:
        verbose_name = "Membership Application"
        verbose_name_plural = "Membership Applications"
        ordering = ["-submitted_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["submitted_at"]),
            models.Index(fields=["email"]),
            models.Index(fields=["last_name", "first_name"]),
        ]

    def __str__(self):
        return f"{self.first_name} {self.last_name} - {self.get_status_display()}"

    @property
    def full_name(self):
        """Return the full name of the applicant."""
        parts = [self.first_name]
        if self.middle_initial:
            parts.append(f"{self.middle_initial}.")
        parts.append(self.last_name)
        if self.name_suffix:
            parts.append(self.name_suffix)
        return " ".join(parts)

    @property
    def full_address(self):
        """Return the full formatted address."""
        parts = [self.address_line1]
        if self.address_line2:
            parts.append(self.address_line2)
        parts.append(f"{self.city}, {self.state} {self.zip_code}")
        if self.country != "USA":
            parts.append(self.country)
        return "\n".join(parts)

    @property
    def is_pilot(self):
        """Check if the applicant holds any pilot certificates."""
        return (
            self.has_private_pilot
            or self.has_commercial_pilot
            or self.has_cfi
            or (self.glider_rating and self.glider_rating != "none")
        )

    @property
    def has_soaring_experience(self):
        """Check if the applicant has any soaring/glider flight experience."""
        return (self.glider_flight_hours or 0) > 0

    def can_be_approved(self):
        """Check if the application has all required information for approval."""
        required_fields = [
            self.first_name,
            self.last_name,
            self.email,
            self.phone,
            self.address_line1,
            self.city,
            self.state,
            self.zip_code,
            self.emergency_contact_name,
            self.emergency_contact_phone,
        ]

        # All required fields must be filled
        if not all(required_fields):
            return False

        # Must agree to terms
        if not (
            self.agrees_to_terms
            and self.agrees_to_safety_rules
            and self.agrees_to_financial_obligations
        ):
            return False

        return True

    def approve_application(self, reviewed_by=None):
        """
        Approve the application and create a member account.
        Returns the created Member instance.
        """
        if not self.can_be_approved():
            raise ValueError(
                "Application cannot be approved - missing required information"
            )

        if self.status == "approved" and self.member_account:
            return self.member_account

        # Import Member here to avoid circular imports
        from django.db import IntegrityError

        from members.models import Member
        from members.utils.username import generate_username

        # Create the member account, retrying if a race condition produces a
        # username collision between generate_username()'s exists() check and
        # the actual INSERT.
        while True:
            try:
                member = Member.objects.create_user(
                    username=generate_username(self.first_name, self.last_name),
                    email=self.email,
                    first_name=self.first_name,
                    last_name=self.last_name,
                )
                break
            except IntegrityError:
                pass  # username claimed between check and insert; retry with next suffix

        # Set additional member fields from application
        member.middle_initial = self.middle_initial
        member.name_suffix = self.name_suffix
        member.phone = self.phone
        member.mobile_phone = self.mobile_phone
        member.address = self.full_address
        member.city = self.city
        member.state_code = self.state if len(self.state) <= 2 else self.state[:2]
        member.state_freeform = self.state if len(self.state) > 2 else ""
        member.zip_code = self.zip_code
        member.country = self.country[:2] if self.country in ["USA", "US"] else "US"
        member.emergency_contact = f"{self.emergency_contact_name} ({self.emergency_contact_relationship}): {self.emergency_contact_phone}"

        # Aviation information
        if self.pilot_certificate_number:
            member.pilot_certificate_number = self.pilot_certificate_number
        member.glider_rating = self.glider_rating
        member.SSA_member_number = self.ssa_member_number

        # Set initial membership status (configurable per club)
        config = SiteConfiguration.objects.first()
        if config and hasattr(config, "new_member_status"):
            member.membership_status = config.new_member_status
        else:
            member.membership_status = "Probationary Member"  # Default

        # Member starts as inactive until they complete onboarding
        member.is_active = False
        member.save()

        # Update application status
        self.status = "approved"
        self.member_account = member
        self.reviewed_by = reviewed_by
        self.reviewed_at = timezone.now()
        self.save(
            update_fields=["status", "member_account", "reviewed_by", "reviewed_at"]
        )

        return member

    def reject_application(self, reviewed_by=None):
        """Reject the application."""
        self.status = "rejected"
        self.reviewed_by = reviewed_by
        self.reviewed_at = timezone.now()
        self.save(update_fields=["status", "reviewed_by", "reviewed_at"])

    def add_to_waitlist(self, reviewed_by=None):
        """Add the application to the waiting list.

        If already waitlisted, does not change position (prevents duplicate
        position bugs when clicking 'Add to Waitlist' on an already-waitlisted
        application).
        """
        # If already waitlisted, don't reassign position
        if self.status == "waitlisted" and self.waitlist_position:
            return

        # Find the next position on the waitlist
        max_position = MembershipApplication.objects.filter(
            status="waitlisted"
        ).aggregate(max_pos=models.Max("waitlist_position"))["max_pos"]

        self.waitlist_position = (max_position or 0) + 1
        self.status = "waitlisted"
        self.reviewed_by = reviewed_by
        self.reviewed_at = timezone.now()
        self.save(
            update_fields=["status", "waitlist_position", "reviewed_by", "reviewed_at"]
        )
