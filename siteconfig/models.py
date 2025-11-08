import logging
from io import BytesIO

from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.db import models

from utils.favicon import generate_favicon_from_logo
from utils.upload_entropy import upload_site_logo


class SiteConfiguration(models.Model):
    club_name = models.CharField(max_length=200)
    domain_name = models.CharField(
        max_length=200, help_text="Primary domain name (e.g. example.org)"
    )
    club_abbreviation = models.CharField(
        max_length=20, help_text="Short abbreviation (e.g. SSS)"
    )
    club_logo = models.ImageField(upload_to=upload_site_logo, blank=True, null=True)
    club_nickname = models.CharField(
        max_length=40, blank=True, help_text="Nickname or short name (e.g. Skyline)"
    )

    # Contact information
    contact_welcome_text = models.TextField(
        blank=True,
        default="Interested in learning to fly gliders? Have questions about our club? We'd love to hear from you! Fill out the form below and one of our member managers will get back to you soon.",
        help_text="Welcome text displayed on the contact form page",
    )
    contact_response_info = models.TextField(
        blank=True,
        default="Our member managers will receive your message immediately\nWe typically respond within 24-48 hours\nFor urgent questions, feel free to visit us at the airfield during operations\nAll contact information is kept private and not shared with third parties",
        help_text="Information about what happens after contact form submission (one item per line)",
    )

    # Club location
    club_address_line1 = models.CharField(
        max_length=100, blank=True, help_text="Street address line 1"
    )
    club_address_line2 = models.CharField(
        max_length=100, blank=True, help_text="Street address line 2 (optional)"
    )
    club_city = models.CharField(max_length=50, blank=True, help_text="City")
    club_state = models.CharField(max_length=50, blank=True, help_text="State/Province")
    club_zip_code = models.CharField(
        max_length=20, blank=True, help_text="ZIP/Postal code"
    )
    club_country = models.CharField(
        max_length=50, blank=True, default="USA", help_text="Country"
    )

    # Contact methods
    club_phone = models.CharField(
        max_length=20, blank=True, help_text="Main club phone number (optional)"
    )
    operations_info = models.TextField(
        blank=True,
        default="We typically fly on weekends and some weekdays when weather permits. Check our calendar or contact us for current schedule information.",
        help_text="Information about club operations schedule",
    )

    # Scheduling options
    schedule_instructors = models.BooleanField(
        default=False, help_text="We schedule Instructors ahead of time"
    )
    schedule_tow_pilots = models.BooleanField(
        default=False, help_text="We schedule tow pilots ahead of time"
    )
    schedule_duty_officers = models.BooleanField(
        default=False, help_text="We schedule Duty Officers ahead of time"
    )
    schedule_assistant_duty_officers = models.BooleanField(
        default=False, help_text="We schedule Assistant Duty Officers ahead of time"
    )

    # Terminology (customizable titles for all roles)
    duty_officer_title = models.CharField(
        max_length=40,
        default="Duty Officer",
        help_text="We refer to the position of Duty Officer as ...",
    )
    assistant_duty_officer_title = models.CharField(
        max_length=40,
        default="Assistant Duty Officer",
        help_text="We refer to the position of Assistant Duty Officer as ...",
    )
    towpilot_title = models.CharField(
        max_length=40,
        default="Tow Pilot",
        help_text="We refer to the position of Tow Pilot as ...",
    )
    surge_towpilot_title = models.CharField(
        max_length=40,
        default="Surge Tow Pilot",
        blank=True,
        help_text="We refer to the position of Surge Tow Pilot as ... (optional)",
    )
    instructor_title = models.CharField(
        max_length=40,
        default="Instructor",
        help_text="We refer to the position of Instructor as ...",
    )
    surge_instructor_title = models.CharField(
        max_length=40,
        default="Surge Instructor",
        blank=True,
        help_text="We refer to the position of Surge Instructor as ... (optional)",
    )
    membership_manager_title = models.CharField(
        max_length=40,
        default="Membership Manager",
        help_text="We refer to the person who manages the membership as ...",
    )
    equipment_manager_title = models.CharField(
        max_length=40,
        default="Equipment Manager",
        help_text="We refer to the person who manages the equipment as ...",
    )

    # Reservation options
    allow_glider_reservations = models.BooleanField(
        default=False,
        help_text="We allow members to reserve club gliders ahead of time.",
    )
    allow_two_seater_reservations = models.BooleanField(
        default=False,
        help_text="We allow members to reserve club two seaters ahead of time.",
    )

    # Notification dedupe: number of minutes to suppress duplicate redaction
    # notifications for the same member URL. Editable by the Webmaster in the
    # admin SiteConfiguration UI. If blank/zero, falls back to settings or
    # application default.
    redaction_notification_dedupe_minutes = models.PositiveIntegerField(
        default=60,
        help_text="Dedupe window (minutes) for member redaction notifications.",
    )

    # Operational Calendar Configuration
    operations_start_period = models.CharField(
        max_length=100,
        blank=True,
        default="First weekend of May",
        help_text="When club operations typically start each year. Examples: 'First weekend of May', '1st weekend of Apr', 'Second weekend in March', 'Last weekend Oct'. Supports: first/1st, second/2nd, third/3rd, fourth/4th, last + full month names or abbreviations (Jan, Feb, Mar, Apr, May, Jun, Jul, Aug, Sep, Oct, Nov, Dec)",
    )
    operations_end_period = models.CharField(
        max_length=100,
        blank=True,
        default="Last weekend of October",
        help_text="When club operations typically end each year. Examples: 'Last weekend of October', '2nd weekend of Dec', 'Third weekend in November'. Leave both fields blank to include all dates year-round.",
    )

    def clean(self):
        if SiteConfiguration.objects.exclude(id=self.id).exists():
            raise ValidationError("Only one SiteConfiguration instance allowed.")

        # Validate operational period formats
        # Local import to avoid circular dependency
        from duty_roster.operational_calendar import parse_operational_period

        if self.operations_start_period:
            try:
                parse_operational_period(self.operations_start_period)
            except ValueError as e:
                raise ValidationError(
                    {"operations_start_period": f"Invalid format: {e}"}
                )

        if self.operations_end_period:
            try:
                parse_operational_period(self.operations_end_period)
            except ValueError as e:
                raise ValidationError({"operations_end_period": f"Invalid format: {e}"})

    def save(self, *args, **kwargs):
        self.full_clean()
        is_new_logo = False
        if self.pk:
            old = SiteConfiguration.objects.get(pk=self.pk)
            if old.club_logo != self.club_logo:
                is_new_logo = True
        else:
            is_new_logo = bool(self.club_logo)
        super().save(*args, **kwargs)
        # Generate favicon if logo was uploaded/changed
        if self.club_logo and is_new_logo:
            # Save favicon.ico at MEDIA_ROOT/favicon.ico using storage backend
            try:
                with self.club_logo.open("rb") as logo_file:
                    # Generate favicon in memory
                    from io import BytesIO

                    outbuf = BytesIO()
                    generate_favicon_from_logo(logo_file, outbuf)
                    outbuf.seek(0)
                    # Save to storage as 'favicon.ico' at root of MEDIA
                    default_storage.save("favicon.ico", outbuf)
            except Exception as e:
                # Log storage or favicon generation errors but don't break model save
                logging.exception(f"Failed to save favicon.ico to default_storage: {e}")

    def __str__(self):
        return f"Site Configuration for {self.club_name}"


class MembershipStatus(models.Model):
    """
    Configurable membership statuses for the club.
    This replaces the hardcoded membership status lists in members.constants.
    """

    name = models.CharField(
        max_length=50,
        unique=True,
        help_text="The display name for this membership status (e.g., 'Full Member')",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether members with this status are considered 'active' and can access member features",
    )
    sort_order = models.PositiveIntegerField(
        default=100,
        help_text="Sort order for display in dropdowns and lists (lower numbers appear first)",
    )
    description = models.TextField(
        blank=True,
        help_text="Optional description of what this membership status means",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Membership Status"
        verbose_name_plural = "Membership Statuses"
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name

    def delete(self, *args, **kwargs):
        """Override delete to prevent deletion if members are using this status."""
        # Import here to avoid circular imports
        try:
            from django.core.exceptions import ValidationError

            from members.models import Member

            member_count = Member.objects.filter(membership_status=self.name).count()
            if member_count > 0:
                raise ValidationError(
                    f'Cannot delete membership status "{self.name}" - '
                    f"{member_count} members currently have this status. "
                    f"Change their status first, then delete this membership status."
                )
        except ImportError:
            # During migrations, Member model might not be available
            pass

        super().delete(*args, **kwargs)

    @classmethod
    def get_active_statuses(cls):
        """Get all membership statuses that are marked as active."""
        return cls.objects.filter(is_active=True).values_list("name", flat=True)

    @classmethod
    def get_all_status_choices(cls):
        """Get all membership statuses as Django field choices."""
        return [
            (status.name, status.name)
            for status in cls.objects.all().order_by("sort_order", "name")
        ]
