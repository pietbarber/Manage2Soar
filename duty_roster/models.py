from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from members.models import Member
from siteconfig.models import SiteConfiguration


class MemberBlackout(models.Model):
    member = models.ForeignKey(Member, on_delete=models.CASCADE)
    date = models.DateField()
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        unique_together = ("member", "date")
        ordering = ["date"]

    def __str__(self):
        return f"{self.member.full_display_name} unavailable on {self.date}"


class DutyPreference(models.Model):
    member = models.OneToOneField(Member, on_delete=models.CASCADE)
    preferred_day = models.CharField(
        max_length=10,
        choices=[("sat", "Saturday"), ("sun", "Sunday")],
        blank=True,
        null=True,
    )
    comment = models.TextField(blank=True, null=True)
    dont_schedule = models.BooleanField(default=False)
    scheduling_suspended = models.BooleanField(default=False)
    suspended_reason = models.CharField(max_length=255, blank=True, null=True)
    last_duty_date = models.DateField(blank=True, null=True)

    instructor_percent = models.PositiveIntegerField(default=0)
    duty_officer_percent = models.PositiveIntegerField(default=0)
    ado_percent = models.PositiveIntegerField(default=0)
    towpilot_percent = models.PositiveIntegerField(default=0)
    MAX_ASSIGN_CHOICES = [(i, str(i)) for i in range(0, 13)]  # 0–12 times
    max_assignments_per_month = models.PositiveIntegerField(
        choices=MAX_ASSIGN_CHOICES,
        default=2,
        help_text="How many times per month you’d like to be scheduled",
    )

    allow_weekend_double = models.BooleanField(
        default=False,
        help_text="I'm fine being scheduled both Saturday and Sunday on the same weekend",
    )

    def __str__(self):
        return f"Preferences for {self.member.full_display_name}"


class DutyPairing(models.Model):
    member = models.ForeignKey(
        Member, on_delete=models.CASCADE, related_name="pairing_source"
    )
    pair_with = models.ForeignKey(
        Member, on_delete=models.CASCADE, related_name="pairing_target"
    )

    def __str__(self):
        return f"{self.member.full_display_name} prefers to work with {self.pair_with.full_display_name}"


class DutyAvoidance(models.Model):
    member = models.ForeignKey(
        Member, on_delete=models.CASCADE, related_name="avoid_source"
    )
    avoid_with = models.ForeignKey(
        Member, on_delete=models.CASCADE, related_name="avoid_target"
    )

    def __str__(self):
        return f"{self.member.full_display_name} must not work with {self.avoid_with.full_display_name}"


class DutyAssignment(models.Model):
    date = models.DateField(unique=True)

    # Primary duty roles
    duty_officer = models.ForeignKey(
        Member,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="as_duty_officer",
    )
    assistant_duty_officer = models.ForeignKey(
        Member, null=True, blank=True, on_delete=models.SET_NULL, related_name="as_ado"
    )
    instructor = models.ForeignKey(
        Member,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="as_instructor",
    )
    surge_instructor = models.ForeignKey(
        Member,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="as_surge_instructor",
    )
    tow_pilot = models.ForeignKey(
        Member,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="as_tow_pilot",
    )
    surge_tow_pilot = models.ForeignKey(
        Member,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="as_surge_tow_pilot",
    )
    surge_notified = models.BooleanField(default=False)  # for instructor emails
    tow_surge_notified = models.BooleanField(default=False)  # for tow pilot emails

    # Location & scheduling
    location = models.ForeignKey(
        "logsheet.Airfield", null=True, blank=True, on_delete=models.SET_NULL
    )
    # True = scheduled ops, False = ad-hoc
    is_scheduled = models.BooleanField(default=True)
    # Only used if is_scheduled is False
    is_confirmed = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["date"]

    def __str__(self):
        return f"{self.date} @ {self.location.identifier if self.location else 'Unknown Field'}"


class InstructionSlot(models.Model):
    """
    Represents a student's request for instruction on a specific duty day.

    Workflow:
    1. Student sees instructor scheduled, requests instruction (status=pending)
    2. Instructor reviews request, accepts or rejects (instructor_response)
    3. If accepted, student is notified and slot is confirmed
    4. If rejected, student is notified and can try another date
    """

    # Instruction type choices - what kind of instruction the student wants
    INSTRUCTION_TYPE_CHOICES = [
        ("field_check", "Field Check"),
        ("general", "General Instruction"),
        ("flight_review", "Flight Review (BFR)"),
        ("wings", "WINGS Program"),
        ("pre_solo", "Pre-Solo Practice"),
        ("checkride_prep", "Checkride Preparation"),
        ("other", "Other (see notes)"),
    ]

    assignment = models.ForeignKey(
        "DutyAssignment", on_delete=models.CASCADE, related_name="instruction_slots"
    )
    student = models.ForeignKey(
        Member, on_delete=models.CASCADE, related_name="instruction_requests"
    )
    instructor = models.ForeignKey(
        Member,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_students",
        help_text="The instructor assigned to work with this student",
    )

    # Student's instruction request details
    instruction_types = models.JSONField(
        default=list,
        blank=True,
        help_text="List of instruction types requested (e.g., ['field_check', 'general'])",
    )
    student_notes = models.TextField(
        blank=True,
        help_text="Additional notes from student about what they want to work on",
    )

    # Student's request status (from student's perspective)
    STATUS_CHOICES = [
        ("pending", "Pending"),  # Student has requested, awaiting instructor response
        ("confirmed", "Confirmed"),  # Instructor accepted, student is scheduled
        ("waitlist", "Waitlist"),  # Student is on waitlist for this day
        ("cancelled", "Cancelled"),  # Student cancelled their request
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")

    # Instructor's response (from instructor's perspective)
    INSTRUCTOR_RESPONSE_CHOICES = [
        ("pending", "Pending"),  # Instructor hasn't responded yet
        ("accepted", "Accepted"),  # Instructor accepted this student
        ("rejected", "Rejected"),  # Instructor declined this student
    ]
    instructor_response = models.CharField(
        max_length=20,
        choices=INSTRUCTOR_RESPONSE_CHOICES,
        default="pending",
        help_text="Instructor's response to the student's request",
    )

    # Optional note from instructor (e.g., reason for rejection, scheduling note)
    instructor_note = models.TextField(
        blank=True,
        help_text="Optional note from instructor to student",
    )

    # Track when instructor responded
    instructor_response_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the instructor responded to this request",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["assignment__date", "created_at"]
        unique_together = ["assignment", "student"]  # One request per student per day

    def __str__(self):
        return f"{self.student.full_display_name} for {self.assignment.date} ({self.status})"

    def get_instruction_types_display(self):
        """Return human-readable list of instruction types requested."""
        type_map = dict(self.INSTRUCTION_TYPE_CHOICES)
        return [type_map.get(t, t) for t in self.instruction_types]

    def get_instruction_types_text(self):
        """Return comma-separated string of instruction types."""
        types = self.get_instruction_types_display()
        if not types:
            return "Not specified"
        return ", ".join(types)

    def accept(self, instructor, note=""):
        """Instructor accepts this student's request."""
        self.instructor = instructor
        self.instructor_response = "accepted"
        self.status = "confirmed"
        self.instructor_note = note
        self.instructor_response_at = timezone.now()
        self.save()

    def reject(self, note=""):
        """Instructor rejects this student's request."""
        self.instructor_response = "rejected"
        self.status = "cancelled"
        self.instructor_note = note
        self.instructor_response_at = timezone.now()
        self.save()


class DutySwapRequest(models.Model):
    """
    Represents a request from a duty crew member who needs coverage for their assigned duty.

    Workflow:
    1. Member sees they're scheduled, clicks "Request Swap" (status=open)
    2. Request goes to all eligible members OR a specific member (request_type)
    3. Other members can make offers (DutySwapOffer)
    4. Requester accepts an offer → swap/cover completed (status=fulfilled)
    5. If no offers by deadline → escalates to Duty Officer
    """

    # Static role keys; display titles are resolved at runtime
    ROLE_CHOICES = [
        ("DO", "Duty Officer"),
        ("ADO", "Assistant Duty Officer"),
        ("INSTRUCTOR", "Instructor"),
        ("TOW", "Tow Pilot"),
    ]

    REQUEST_TYPE_CHOICES = [
        ("general", "General Broadcast"),  # Sent to all eligible members
        ("direct", "Direct Request"),  # Sent to specific member only
    ]

    STATUS_CHOICES = [
        ("open", "Open"),  # Request is active, accepting offers
        ("fulfilled", "Fulfilled"),  # An offer was accepted, swap complete
        ("cancelled", "Cancelled"),  # Requester cancelled the request
        ("expired", "Expired"),  # Duty day passed without resolution
    ]

    requester = models.ForeignKey(
        Member, on_delete=models.CASCADE, related_name="swap_requests"
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    original_date = models.DateField()

    request_type = models.CharField(
        max_length=10, choices=REQUEST_TYPE_CHOICES, default="general"
    )
    # For direct requests, who was specifically asked
    direct_request_to = models.ForeignKey(
        Member,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="swap_requests_received",
        help_text="If direct request, the specific member asked",
    )

    # Note from requester explaining why they need coverage
    notes = models.TextField(blank=True, help_text="Reason for needing coverage")

    is_emergency = models.BooleanField(
        default=False, help_text="Urgent request (IMSAFE, medical, etc.)"
    )

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="open")

    # Which offer was accepted (if fulfilled)
    accepted_offer = models.OneToOneField(
        "DutySwapOffer",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="fulfilled_request",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    fulfilled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    # Legacy compatibility
    @property
    def is_fulfilled(self):
        return self.status == "fulfilled"

    def get_role_title(self):
        """Get the display title for this role from site config."""
        from siteconfig.utils import get_role_title

        role_map = {
            "DO": "duty_officer",
            "ADO": "assistant_duty_officer",
            "INSTRUCTOR": "instructor",
            "TOW": "towpilot",
        }
        return get_role_title(role_map.get(self.role, self.role))

    def is_critical_role(self):
        """Returns True if this role is critical for operations (Tow Pilot or DO)."""
        return self.role in ("DO", "TOW")

    def days_until_duty(self):
        """Returns the number of days until the duty date."""
        today = timezone.now().date()
        return (self.original_date - today).days

    def get_urgency_level(self):
        """Returns urgency level: 'normal', 'soon', 'urgent', or 'emergency'."""
        if self.is_emergency:
            return "emergency"
        days = self.days_until_duty()
        if days < 3:
            return "emergency"
        elif days <= 7:
            return "urgent"
        elif days <= 14:
            return "soon"
        else:
            return "normal"

    def __str__(self):
        role_title = self.get_role_title()
        return f"{role_title} swap for {self.original_date} by {self.requester.full_display_name}"


class DutySwapOffer(models.Model):
    """
    Represents an offer from a member to help with a swap request.

    Workflow:
    1. Member sees open swap request
    2. Member creates offer (cover or swap with proposed date)
    3. Requester reviews offers, accepts one
    4. Accepted offer triggers duty assignment updates
    5. Other pending offers are auto-declined
    """

    swap_request = models.ForeignKey(
        "DutySwapRequest", on_delete=models.CASCADE, related_name="offers"
    )
    offered_by = models.ForeignKey(
        Member, on_delete=models.CASCADE, related_name="swap_offers_made"
    )

    OFFER_TYPE_CHOICES = [
        ("cover", "Cover (I'll take your shift)"),
        ("swap", "Swap (I'll take yours if you take mine)"),
    ]
    offer_type = models.CharField(max_length=10, choices=OFFER_TYPE_CHOICES)

    # Used only if offer_type == 'swap'
    proposed_swap_date = models.DateField(
        null=True, blank=True, help_text="Date offerer wants requester to take"
    )

    # Note from offerer (optional)
    notes = models.TextField(blank=True, help_text="Optional note about the offer")

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("accepted", "Accepted"),
        ("declined", "Declined"),
        ("auto_declined", "Auto-declined"),  # When another offer was accepted
        ("withdrawn", "Withdrawn"),  # Offerer withdrew their offer
    ]
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default="pending")

    # Track if proposed date is in requester's blackout
    is_blackout_conflict = models.BooleanField(
        default=False, help_text="True if proposed swap date is in requester's blackout"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def check_blackout_conflict(self):
        """Check if proposed swap date conflicts with requester's blackout dates."""
        if self.offer_type != "swap" or not self.proposed_swap_date:
            return False

        # MemberBlackout is already defined in this module, no import needed

        return MemberBlackout.objects.filter(
            member=self.swap_request.requester, date=self.proposed_swap_date
        ).exists()

    def save(self, *args, **kwargs):
        # Auto-check blackout conflict before saving
        if self.offer_type == "swap" and self.proposed_swap_date:
            self.is_blackout_conflict = self.check_blackout_conflict()
        super().save(*args, **kwargs)

    def __str__(self):
        if self.offer_type == "swap" and self.proposed_swap_date:
            return f"{self.offered_by.full_display_name} offers swap ({self.proposed_swap_date}) for {self.swap_request.original_date}"
        return f"{self.offered_by.full_display_name} offers to cover {self.swap_request.original_date}"


class OpsIntent(models.Model):
    member = models.ForeignKey(Member, on_delete=models.CASCADE)
    date = models.DateField()
    # e.g. ["towpilot", "glider_pilot", "instruction"]
    # Centralize available activities so templates and admin can render
    # consistent labels. Keys here are stored in the JSONField.
    AVAILABLE_ACTIVITIES = [
        ("instruction", "Instruction"),
        ("club", "Club glider"),
        ("private", "Private glider"),
        ("towpilot", "Tow Pilot"),
        ("glider_pilot", "Glider Pilot"),
    ]

    available_as = models.JSONField(default=list)
    glider = models.ForeignKey(
        "logsheet.Glider", null=True, blank=True, on_delete=models.SET_NULL
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("member", "date")

    def __str__(self):
        return f"{self.member.full_display_name} available on {self.date}"

    def available_as_labels(self):
        """Return a list of human-friendly labels for the stored activity keys."""
        mapping = dict(self.AVAILABLE_ACTIVITIES)
        return [mapping.get(k, k) for k in (self.available_as or [])]


class GliderReservation(models.Model):
    """
    Glider reservation system for members to reserve club gliders ahead of time.

    Key features:
    - Members can reserve gliders for specific dates and time slots
    - Tracks yearly reservation count per member
    - SiteConfiguration controls enable/disable and max reservations per year
    - Considers whether glider is a trainer (2-seater)
    - Integrated with logsheet reminders and daily ops email

    See Issue #410 and docs/workflows/issue-190-glider-reservation-design.md
    """

    # Core reservation data
    member = models.ForeignKey(
        "members.Member",
        on_delete=models.CASCADE,
        related_name="glider_reservations",
    )
    glider = models.ForeignKey(
        "logsheet.Glider",
        on_delete=models.CASCADE,
        related_name="reservations",
    )
    date = models.DateField(
        db_index=True,
        help_text="Date of the reserved flight",
    )
    start_time = models.TimeField(
        blank=True,
        null=True,
        help_text="Preferred start time (optional, can be general 'morning' or 'afternoon')",
    )
    end_time = models.TimeField(
        blank=True,
        null=True,
        help_text="Expected end time (optional)",
    )

    # Reservation type
    RESERVATION_TYPE_CHOICES = [
        ("solo", "Solo Flight"),
        ("badge", "Badge Flight"),
        ("guest", "Guest Flying"),
        ("other", "Other"),
    ]
    reservation_type = models.CharField(
        max_length=20,
        choices=RESERVATION_TYPE_CHOICES,
        default="solo",
        help_text="Type of flight operation planned",
    )

    # Time preference (simpler than specific times)
    TIME_PREFERENCE_CHOICES = [
        ("morning", "Morning (first flights)"),
        ("midday", "Midday"),
        ("afternoon", "Afternoon"),
        ("full_day", "Full Day"),
        ("specific", "Specific Time"),
    ]
    time_preference = models.CharField(
        max_length=20,
        choices=TIME_PREFERENCE_CHOICES,
        default="morning",
        help_text="General time preference for the reservation",
    )

    # Status tracking
    STATUS_CHOICES = [
        ("confirmed", "Confirmed"),
        ("cancelled", "Cancelled"),
        ("completed", "Completed"),
        ("no_show", "No Show"),
    ]
    status = models.CharField(
        max_length=15,
        choices=STATUS_CHOICES,
        default="confirmed",
        db_index=True,
    )

    # Additional details
    purpose = models.TextField(
        blank=True,
        help_text="Additional details about the planned flight (badge attempt details, guest info, etc.)",
    )

    # Cancellation tracking
    cancelled_at = models.DateTimeField(
        blank=True,
        null=True,
        help_text="When the reservation was cancelled",
    )
    cancellation_reason = models.TextField(
        blank=True,
        help_text="Reason for cancellation",
    )

    # Administrative tracking
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["date", "time_preference", "start_time"]
        indexes = [
            models.Index(fields=["date", "glider"]),
            models.Index(fields=["member", "date"]),
            models.Index(fields=["date", "status"]),
        ]
        # Prevent double-booking: one glider can have one active reservation per day/time
        constraints = [
            models.UniqueConstraint(
                fields=["glider", "date", "time_preference"],
                condition=models.Q(status="confirmed"),
                name="unique_active_reservation_per_slot",
            ),
        ]

    def __str__(self):
        glider_str = str(self.glider) if self.glider else "Unknown Glider"
        member_str = (
            self.member.full_display_name
            if self.member and hasattr(self.member, "full_display_name")
            else "Unknown Member"
        )
        return f"{member_str} - {glider_str} on {self.date}"

    @property
    def is_active(self):
        """Check if this reservation is still active (confirmed and in the future)."""
        return self.status == "confirmed" and self.date >= timezone.now().date()

    @property
    def is_trainer(self):
        """Check if the reserved glider is a trainer (2-seater)."""
        return self.glider and self.glider.seats >= 2

    @classmethod
    def get_member_yearly_count(cls, member, year=None):
        """
        Get the count of reservations a member has made for a given year.
        Used to enforce max_reservations_per_year limit.
        """
        if year is None:
            year = timezone.now().year

        return cls.objects.filter(
            member=member,
            date__year=year,
            status__in=["confirmed", "completed"],  # Don't count cancelled/no-show
        ).count()

    @classmethod
    def get_member_monthly_count(cls, member, year=None, month=None):
        """
        Get the count of reservations a member has made for a given month.
        Used to enforce max_reservations_per_month limit.
        """
        if year is None:
            year = timezone.now().year
        if month is None:
            month = timezone.now().month

        return cls.objects.filter(
            member=member,
            date__year=year,
            date__month=month,
            status__in=["confirmed", "completed"],  # Don't count cancelled/no-show
        ).count()

    @classmethod
    def get_reservations_by_year(cls, member):
        """
        Return reservation counts grouped by year for a member.
        Returns a dict like {2024: 3, 2025: 1}
        """
        from django.db.models import Count
        from django.db.models.functions import ExtractYear

        return dict(
            cls.objects.filter(
                member=member,
                status__in=["confirmed", "completed"],
            )
            .annotate(year=ExtractYear("date"))
            .values("year")
            .annotate(count=Count("id"))
            .values_list("year", "count")
        )

    @classmethod
    def get_reservations_for_date(cls, date):
        """Get all confirmed reservations for a specific date."""
        return cls.objects.filter(date=date, status="confirmed").select_related(
            "member", "glider"
        )

    @classmethod
    def can_member_reserve(cls, member, year=None, month=None):
        """
        Check if a member can make a new reservation based on yearly and monthly limits.
        Returns tuple: (can_reserve: bool, message: str)
        """
        config = SiteConfiguration.objects.first()
        if not config:
            return False, "Site configuration is not available."

        # Check if reservations are enabled
        if not config.allow_glider_reservations:
            return False, "Glider reservations are currently disabled."

        # Check yearly limit (0 = unlimited)
        max_per_year = config.max_reservations_per_year
        if max_per_year > 0:
            current_count = cls.get_member_yearly_count(member, year)
            if current_count >= max_per_year:
                return (
                    False,
                    f"You have reached your limit of {max_per_year} reservations for this year.",
                )

        # Check monthly limit (0 = unlimited)
        max_per_month = config.max_reservations_per_month
        if max_per_month > 0:
            monthly_count = cls.get_member_monthly_count(member, year, month)
            if monthly_count >= max_per_month:
                return (
                    False,
                    f"You have reached your limit of {max_per_month} reservations for this month.",
                )

        return True, "OK"

    def clean(self):
        """Validate the reservation before saving."""
        from django.db import transaction

        # Check if glider is grounded
        if self.glider and self.glider.is_grounded:
            raise ValidationError(
                f"Glider {self.glider} is currently grounded and cannot be reserved."
            )

        # Check if glider is club-owned (private gliders shouldn't be reservable)
        if self.glider and not self.glider.club_owned:
            raise ValidationError(
                f"Glider {self.glider} is privately owned and cannot be reserved through this system."
            )

        # Check if glider is active
        if self.glider and not self.glider.is_active:
            raise ValidationError(f"Glider {self.glider} is not currently active.")

        # For two-seater reservations, check site config
        if self.glider and self.glider.seats >= 2:
            config = SiteConfiguration.objects.first()
            if config and not config.allow_two_seater_reservations:
                raise ValidationError(
                    "Two-seater glider reservations are not currently allowed."
                )

        # Validate times if specific time preference
        if self.time_preference == "specific":
            if not self.start_time:
                raise ValidationError(
                    "Start time is required when using specific time preference."
                )

        # Check for existing reservation conflicts (use transaction and locking to prevent race conditions)
        # NOTE: select_for_update() only provides effective locking if the entire validation-save
        # cycle is within a transaction. The form's clean() method wraps the yearly limit check
        # in transaction.atomic() for that specific query. The UniqueConstraint at the database
        # level provides the final safety net against race conditions.
        if self.status == "confirmed":
            with transaction.atomic():
                # Lock existing reservations for this glider/date to prevent concurrent modifications
                conflicts = (
                    GliderReservation.objects.filter(
                        glider=self.glider,
                        date=self.date,
                        status="confirmed",
                    )
                    .exclude(pk=self.pk if self.pk else None)
                    .select_for_update()
                )

                # Same time preference or full day conflicts
                if self.time_preference == "full_day":
                    # Full day conflicts with any other reservation
                    if conflicts.exists():
                        raise ValidationError(
                            f"Glider {self.glider} is reserved for the full day on {self.date}."
                        )
                else:
                    # Check for overlapping time preferences
                    if conflicts.filter(time_preference="full_day").exists():
                        raise ValidationError(
                            f"Glider {self.glider} is reserved for the full day on {self.date}."
                        )
                    if conflicts.filter(time_preference=self.time_preference).exists():
                        raise ValidationError(
                            f"Glider {self.glider} is already reserved for {self.get_time_preference_display()} on {self.date}."
                        )

    def cancel(self, reason=""):
        """Cancel this reservation."""
        self.status = "cancelled"
        self.cancelled_at = timezone.now()
        self.cancellation_reason = reason
        self.save()

    def mark_completed(self):
        """Mark this reservation as completed (flight happened)."""
        self.status = "completed"
        self.save()

    def mark_no_show(self):
        """Mark this reservation as no-show (member didn't show up)."""
        self.status = "no_show"
        self.save()
