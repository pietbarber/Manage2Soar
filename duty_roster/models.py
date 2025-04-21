from django.db import models
from members.models import Member

class DutyDay(models.Model):
    date = models.DateField(unique=True)
    notes = models.TextField(blank=True)

    def __str__(self):
        return self.date.strftime("%A, %B %d, %Y")


class DutySlot(models.Model):
    ROLE_CHOICES = [
        ('duty_officer', 'Duty Officer'),
        ('assistant_duty_officer', 'Assistant Duty Officer'),
        ('instructor', 'Instructor'),
        ('surge_instructor', 'Surge Instructor'),
        ('tow_pilot', 'Tow Pilot'),
        ('surge_tow_pilot', 'Surge Tow Pilot'),
    ]

    duty_day = models.ForeignKey(DutyDay, on_delete=models.CASCADE, related_name="slots")
    member = models.ForeignKey(Member, on_delete=models.CASCADE)
    role = models.CharField(max_length=32, choices=ROLE_CHOICES)

    class Meta:
        unique_together = ('duty_day', 'role')
        ordering = ['duty_day', 'role']

    def __str__(self):
        return f"{self.duty_day.date} – {self.get_role_display()} – {self.member.full_display_name}"


class MemberBlackout(models.Model):
    member = models.ForeignKey(Member, on_delete=models.CASCADE)
    date = models.DateField()
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        unique_together = ('member', 'date')
        ordering = ['date']

    def __str__(self):
        return f"{self.member.full_display_name} unavailable on {self.date}"

class DutyPreference(models.Model):
    member = models.OneToOneField(Member, on_delete=models.CASCADE)
    preferred_day = models.CharField(
        max_length=10,
        choices=[("sat", "Saturday"), ("sun", "Sunday")],
        blank=True,
        null=True
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
    max_assignments_per_month = models.PositiveIntegerField(default=2)  # NEW FIELD

    def __str__(self):
        return f"Preferences for {self.member.full_display_name}"


class DutyPairing(models.Model):
    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="pairing_source")
    pair_with = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="pairing_target")

    def __str__(self):
        return f"{self.member.full_display_name} prefers to work with {self.pair_with.full_display_name}"

class DutyAvoidance(models.Model):
    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="avoid_source")
    avoid_with = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="avoid_target")

    def __str__(self):
        return f"{self.member.full_display_name} must not work with {self.avoid_with.full_display_name}"
