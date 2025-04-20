from django.db import models

# Create your models here.
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
