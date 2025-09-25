from django.db import models
from django.core.exceptions import ValidationError
from utils.upload_entropy import upload_site_logo


class SiteConfiguration(models.Model):
    club_name = models.CharField(max_length=200)
    domain_name = models.CharField(
        max_length=200, help_text="Primary domain name (e.g. example.org)")
    club_abbreviation = models.CharField(
        max_length=20, help_text="Short abbreviation (e.g. SSS)")
    club_logo = models.ImageField(
        upload_to=upload_site_logo, blank=True, null=True)
    club_nickname = models.CharField(
        max_length=40, blank=True, help_text="Nickname or short name (e.g. Skyline)")

    # Scheduling options
    schedule_instructors = models.BooleanField(
        default=False, help_text="We schedule Instructors ahead of time")
    schedule_tow_pilots = models.BooleanField(
        default=False, help_text="We schedule tow pilots ahead of time")
    schedule_duty_officers = models.BooleanField(
        default=False, help_text="We schedule Duty Officers ahead of time")
    schedule_assistant_duty_officers = models.BooleanField(
        default=False, help_text="We schedule Assistant Duty Officers ahead of time")

    # Terminology (customizable titles for all roles)
    duty_officer_title = models.CharField(
        max_length=40, default="Duty Officer", help_text="We refer to the position of Duty Officer as ...")
    assistant_duty_officer_title = models.CharField(
        max_length=40, default="Assistant Duty Officer", help_text="We refer to the position of Assistant Duty Officer as ...")
    towpilot_title = models.CharField(
        max_length=40, default="Tow Pilot", help_text="We refer to the position of Tow Pilot as ...")
    surge_towpilot_title = models.CharField(
        max_length=40, default="Surge Tow Pilot", blank=True, help_text="We refer to the position of Surge Tow Pilot as ... (optional)")
    instructor_title = models.CharField(
        max_length=40, default="Instructor", help_text="We refer to the position of Instructor as ...")
    surge_instructor_title = models.CharField(
        max_length=40, default="Surge Instructor", blank=True, help_text="We refer to the position of Surge Instructor as ... (optional)")
    membership_manager_title = models.CharField(
        max_length=40, default="Membership Manager", help_text="We refer to the person who manages the membership as ...")
    equipment_manager_title = models.CharField(
        max_length=40, default="Equipment Manager", help_text="We refer to the person who manages the equipment as ...")

    # Reservation options
    allow_glider_reservations = models.BooleanField(
        default=False, help_text="We allow members to reserve club gliders ahead of time.")
    allow_two_seater_reservations = models.BooleanField(
        default=False, help_text="We allow members to reserve club two seaters ahead of time.")

    def clean(self):
        if SiteConfiguration.objects.exclude(id=self.id).exists():
            raise ValidationError(
                "Only one SiteConfiguration instance allowed.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Site Configuration for {self.club_name}"
