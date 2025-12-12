from django.db import models

from members.models import Member


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

    def accept(self, instructor, note=""):
        """Instructor accepts this student's request."""
        from django.utils import timezone

        self.instructor = instructor
        self.instructor_response = "accepted"
        self.status = "confirmed"
        self.instructor_note = note
        self.instructor_response_at = timezone.now()
        self.save()

    def reject(self, note=""):
        """Instructor rejects this student's request."""
        from django.utils import timezone

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
        from django.utils import timezone

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

        from duty_roster.models import MemberBlackout

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
