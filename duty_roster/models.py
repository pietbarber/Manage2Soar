from django.db import models

from members.models import Member


class DutyDay(models.Model):
    date = models.DateField(unique=True)
    notes = models.TextField(blank=True)

    def __str__(self):
        return self.date.strftime("%A, %B %d, %Y")


class DutySlot(models.Model):
    # Static role keys; display titles are resolved at runtime
    ROLE_CHOICES = [
        ("duty_officer", "Duty Officer"),
        ("assistant_duty_officer", "Assistant Duty Officer"),
        ("instructor", "Instructor"),
        ("surge_instructor", "Surge Instructor"),
        ("tow_pilot", "Tow Pilot"),
        ("surge_tow_pilot", "Surge Tow Pilot"),
    ]

    duty_day = models.ForeignKey(
        DutyDay, on_delete=models.CASCADE, related_name="slots"
    )
    member = models.ForeignKey(Member, on_delete=models.CASCADE)
    role = models.CharField(max_length=32, choices=ROLE_CHOICES)

    class Meta:
        unique_together = ("duty_day", "role")
        ordering = ["duty_day", "role"]

    def __str__(self):
        from siteconfig.utils import get_role_title

        return f"{self.duty_day.date} – {get_role_title(self.role)} – {self.member.full_display_name}"


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

    def __str__(self):
        return f"{self.date} @ {self.location.identifier if self.location else 'Unknown Field'}"


class InstructionSlot(models.Model):
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
    )

    STATUS_CHOICES = [
        ("scheduled", "Scheduled"),
        ("waitlist", "Waitlist"),
        ("cancelled", "Cancelled"),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="waitlist")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.student.full_display_name} for {self.assignment.date} ({self.status})"


class DutySwapRequest(models.Model):
    # Static role keys; display titles are resolved at runtime
    ROLE_CHOICES = [
        ("DO", "Duty Officer"),
        ("ADO", "Assistant Duty Officer"),
        ("INSTRUCTOR", "Instructor"),
        ("TOW", "Tow Pilot"),
    ]

    requester = models.ForeignKey(
        Member, on_delete=models.CASCADE, related_name="swap_requests"
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    original_date = models.DateField()
    is_emergency = models.BooleanField(default=False)  # IMSAFE, medical, etc.
    is_fulfilled = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        from siteconfig.utils import get_role_title

        role_map = {
            "DO": "duty_officer",
            "ADO": "assistant_duty_officer",
            "INSTRUCTOR": "instructor",
            "TOW": "towpilot",
        }
        role_title = get_role_title(role_map.get(self.role, self.role))
        return f"{role_title} swap for {self.original_date} by {self.requester.full_display_name}"


class DutySwapOffer(models.Model):
    swap_request = models.ForeignKey(
        "DutySwapRequest", on_delete=models.CASCADE, related_name="offers"
    )
    offered_by = models.ForeignKey(Member, on_delete=models.CASCADE)

    OFFER_TYPE_CHOICES = [
        ("cover", "Cover (I'll take your shift)"),
        ("swap", "Swap (I'll take yours if you take mine)"),
    ]
    offer_type = models.CharField(max_length=10, choices=OFFER_TYPE_CHOICES)
    # Used only if offer_type == 'swap'
    proposed_swap_date = models.DateField(null=True, blank=True)

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("accepted", "Accepted"),
        ("declined", "Declined"),
    ]
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.offered_by.full_display_name} → {self.swap_request.role} on {self.swap_request.original_date}"


class OpsIntent(models.Model):
    member = models.ForeignKey(Member, on_delete=models.CASCADE)
    date = models.DateField()
    # e.g. ["towpilot", "glider_pilot", "instructor"]
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
