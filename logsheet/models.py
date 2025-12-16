# from .models import Towplane, Airfield  # Adjust import paths as needed
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from tinymce.models import HTMLField

from members.models import Member
from utils.upload_entropy import (
    upload_airfield_photo,
    upload_glider_photo,
    upload_glider_photo_medium,
    upload_glider_photo_small,
    upload_towplane_photo,
    upload_towplane_photo_medium,
    upload_towplane_photo_small,
)

####################################################
# Flight model
#
# This is the biggest model we've got, so pay attention!
#
# This model represents a single flight entry in the logsheet system. It captures details about the flight,
# including the pilot, instructor, glider, towplane, and other relevant information. The model also calculates
# costs associated with the flight, such as tow costs and rental costs, based on the provided data.
# Additionally, it supports splitting costs between members and includes properties for displaying costs
# in a user-friendly format.
#
# Properties:
# - tow_cost_calculated: Calculates the tow cost based on the release altitude and tow rates.
# - rental_cost_calculated: Calculates the rental cost based on the glider's rental rate and flight duration.
# - tow_cost: Retrieves the tow cost based on the release altitude and tow rates.
# - tow_cost_display: Returns a formatted string representation of the tow cost.
# - rental_cost: Calculates the rental cost based on the glider's rental rate and flight duration.
# - rental_cost_display: Returns a formatted string representation of the rental cost.
# - total_cost: Calculates the total cost of the flight (tow cost + rental cost).
# - total_cost_display: Returns a formatted string representation of the total cost.
#
# Methods:
# - save: Overrides the save method to calculate the flight duration based on launch and landing times.
#         Handles overnight flights by adjusting the landing time if it occurs before the launch time.
# - __str__: Returns a string representation of the flight, including the pilot, glider, and launch time.


class Flight(models.Model):
    class Meta:
        indexes = [
            models.Index(fields=["pilot"]),
            models.Index(fields=["instructor"]),
            models.Index(fields=["passenger"]),
            models.Index(fields=["logsheet"]),
            models.Index(fields=["towplane", "logsheet"]),
            models.Index(fields=["tow_pilot", "logsheet"]),
        ]

    logsheet = models.ForeignKey(
        "Logsheet", on_delete=models.CASCADE, related_name="flights"
    )
    launch_time = models.TimeField(blank=True, null=True)
    landing_time = models.TimeField(blank=True, null=True)
    pilot = models.ForeignKey(
        "members.Member",
        on_delete=models.SET_NULL,
        null=True,
        related_name="flights_as_pilot",
    )
    instructor = models.ForeignKey(
        "members.Member",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="flights_as_instructor",
    )
    glider = models.ForeignKey("logsheet.Glider", on_delete=models.SET_NULL, null=True)
    tow_pilot = models.ForeignKey(
        "members.Member",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="flights_as_tow_pilot",
    )
    towplane = models.ForeignKey(
        "Towplane", on_delete=models.SET_NULL, null=True, blank=True
    )
    duration = models.DurationField(blank=True, null=True)
    passenger = models.ForeignKey(
        Member,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="flights_as_passenger",
    )

    # Guest name fallbacks (for legacy import)
    guest_pilot_name = models.CharField(max_length=100, blank=True, null=True)
    guest_instructor_name = models.CharField(max_length=100, blank=True, null=True)
    guest_towpilot_name = models.CharField(max_length=100, blank=True, null=True)

    # Legacy name tracking for post-import cleanup or debug
    passenger_name = models.CharField(
        max_length=100, blank=True, help_text="Name of passenger if not a member"
    )
    legacy_pilot_name = models.CharField(max_length=100, blank=True, null=True)
    legacy_instructor_name = models.CharField(max_length=100, blank=True, null=True)
    legacy_passenger_name = models.CharField(max_length=100, blank=True, null=True)
    legacy_towpilot_name = models.CharField(max_length=100, blank=True, null=True)

    # Launch method for winch/self-launch/other
    class LaunchMethod(models.TextChoices):
        TOWPLANE = "tow", "Towplane"
        WINCH = "winch", "Winch"
        SELF = "self", "Self-Launch"
        OTHER = "other", "Other"

    launch_method = models.CharField(
        max_length=10,
        choices=LaunchMethod.choices,
        default=LaunchMethod.TOWPLANE,
    )
    # Airfield will need to go back in right here.
    airfield = models.ForeignKey("Airfield", on_delete=models.PROTECT, null=True)

    flight_type = models.CharField(max_length=50)  # dual, solo, intro, etc.
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    RELEASE_ALTITUDE_CHOICES = [(i, f"{i} ft") for i in range(0, 7100, 100)]

    release_altitude = models.IntegerField(
        choices=RELEASE_ALTITUDE_CHOICES,
        blank=True,
        null=True,
        help_text="Release altitude in feet (0–7000 in 100ft steps)",
    )
    tow_cost_actual = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True
    )
    rental_cost_actual = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True
    )

    def is_incomplete(self):
        return self.landing_time is not None and (
            self.release_altitude is None
            or self.towplane is None
            or self.tow_pilot is None
        )

    def get_missing_fields(self):
        missing = []
        if self.landing_time is not None:
            if not self.release_altitude:
                missing.append("release altitude")
            if not self.towplane:
                missing.append("towplane")
            if not self.tow_pilot:
                missing.append("tow pilot")
        return missing

    @property
    def status(self):
        if self.landing_time:
            return "landed"
        elif self.launch_time:
            return "flying"
        else:
            return "pending"

    @property
    def tow_cost_calculated(self):
        """
        Calculate tow cost using towplane-specific charging scheme.

        Returns:
            Decimal: The calculated tow cost, or Decimal("0.00") if:
                - free_tow is True (explicitly marked as free)
                - is_retrieve is True AND site config waive_tow_fee_on_retrieve is True
            None: If release_altitude is None or no towplane charge scheme is available.

        Note:
            Instance-level caching of SiteConfiguration via _site_config_cache helps
            reduce queries when this property is accessed multiple times on the same
            Flight instance. For views processing many flights, consider prefetching
            config once and reusing across all instances.
        """
        # Check for free tow flag
        if self.free_tow:
            return Decimal("0.00")

        # Check for retrieve waiver (requires config lookup)
        if self.is_retrieve:
            from siteconfig.models import SiteConfiguration

            config = getattr(self, "_site_config_cache", None)
            if config is None:
                config = SiteConfiguration.objects.first()
                self._site_config_cache = config
            if config and config.waive_tow_fee_on_retrieve:
                return Decimal("0.00")

        if self.release_altitude is None:
            return None

        # Use towplane-specific charge scheme
        if self.towplane:
            try:
                scheme = self.towplane.charge_scheme
                if scheme.is_active:
                    return scheme.calculate_tow_cost(self.release_altitude)
            except TowplaneChargeScheme.DoesNotExist:
                pass

        # No charge scheme available
        return None

    @property
    def rental_cost_calculated(self):
        """
        Calculate rental cost, respecting free flags and waivers.

        Returns:
            Decimal: The calculated rental cost or Decimal("0.00") if:
                - free_rental is True (explicitly marked as free)
                - is_retrieve is True AND site config waive_rental_fee_on_retrieve is True
                - glider has no rental rate
            None: If glider or duration is not set.

        Note:
            Instance-level caching of SiteConfiguration via _site_config_cache helps
            reduce queries when this property is accessed multiple times on the same
            Flight instance.
        """
        # Check for free rental flag
        if self.free_rental:
            return Decimal("0.00")

        # Check for retrieve waiver (requires config lookup)
        if self.is_retrieve:
            from siteconfig.models import SiteConfiguration

            config = getattr(self, "_site_config_cache", None)
            if config is None:
                config = SiteConfiguration.objects.first()
                self._site_config_cache = config
            if config and config.waive_rental_fee_on_retrieve:
                return Decimal("0.00")

        if not self.glider or not self.duration:
            return None
        if not self.glider.rental_rate:
            return Decimal("0.00")
        hours = Decimal(self.duration.total_seconds()) / Decimal(3600)
        return Decimal(str(self.glider.rental_rate)) * hours

    @property
    def tow_cost(self):
        """
        Calculate tow cost using towplane-specific charging scheme.

        This is the same as tow_cost_calculated - keeping both for compatibility.
        """
        return self.tow_cost_calculated

    @property
    def tow_cost_display(self):
        cost = self.tow_cost
        return f"${cost:.2f}" if cost is not None else "—"

    @property
    def rental_cost(self):
        """
        Calculate rental cost with max rental cap applied.

        Delegates free flag and waiver checks to rental_cost_calculated,
        then applies glider's max rental cap if configured.

        Returns:
            Decimal: Final rental cost with cap applied, or Decimal("0.00") if free.
            None: If glider or duration is not set.
        """
        # Get base rental cost (handles free flags and waivers)
        cost = self.rental_cost_calculated

        # If None or $0, return as-is
        if cost is None or cost == Decimal("0.00"):
            return cost

        # Apply max rental cap if set
        if self.glider and self.glider.max_rental_rate is not None:
            max_rate = Decimal(str(self.glider.max_rental_rate))
            cost = min(cost, max_rate)

        return cost.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @property
    def rental_cost_display(self):
        cost = self.rental_cost
        return f"${cost:.2f}" if cost is not None else "—"

    @property
    def total_cost(self):
        tow = self.tow_cost or 0
        rental = self.rental_cost or 0
        return round(tow + rental, 2)

    @property
    def total_cost_display(self):
        return f"${self.total_cost:.2f}" if self.total_cost > 0 else "—"

    def save(self, *args, **kwargs):
        if self.launch_time and self.landing_time:
            launch_dt = datetime.combine(date.today(), self.launch_time)
            land_dt = datetime.combine(date.today(), self.landing_time)

            # Handle overnight flights (if landing before launch)
            if land_dt < launch_dt:
                if (
                    launch_dt - land_dt
                ).total_seconds() < 16 * 3600:  # < 16 hours difference
                    land_dt += timedelta(days=1)
                else:
                    # probably a bad duration, so throw it away
                    self.duration = None
                    super().save(*args, **kwargs)
                    return

            self.duration = land_dt - launch_dt
        else:
            self.duration = None

        super().save(*args, **kwargs)

    split_with = models.ForeignKey(
        Member,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="shared_flights",
    )

    split_type = models.CharField(
        max_length=10,
        choices=[
            ("even", "50/50"),
            ("tow", "Tow Only"),
            ("rental", "Rental Only"),
            ("full", "Full Cost"),
        ],
        null=True,
        blank=True,
    )

    # Special flight type flags (Issue #66)
    is_retrieve = models.BooleanField(
        default=False,
        help_text="This is a retrieve flight (ferrying a glider back after a landout)",
    )
    free_tow = models.BooleanField(
        default=False,
        help_text="No charge for the aerotow (e.g., post-maintenance check flight, club-authorized free flight)",
    )
    free_rental = models.BooleanField(
        default=False,
        help_text="No charge for glider rental (e.g., post-maintenance check flight, club-authorized free flight)",
    )

    def __str__(self):
        return f"{self.pilot} in {self.glider} at {self.launch_time}"


####################################################
# RevisionLog model
#
# This model tracks revisions made to a logsheet. It records details about
# who made the revision, when it was made, and any notes associated with the revision.
# The RevisionLog is used when somebody reactivates a logsheet that was marked as "finalized"
#
# Fields:
# - logsheet: The logsheet that was revised.
# - revised_by: The member who made the revision.
# - revised_at: The timestamp when the revision was made.
# - note: An optional note describing the revision.
#
# Methods:
# - __str__: Returns a string representation of the revision, including the reviser and timestamp.
#
class RevisionLog(models.Model):
    logsheet = models.ForeignKey(
        "Logsheet", on_delete=models.CASCADE, related_name="revisions"
    )
    revised_by = models.ForeignKey(Member, on_delete=models.SET_NULL, null=True)
    revised_at = models.DateTimeField(auto_now_add=True)
    note = models.TextField(blank=True)

    def __str__(self):
        return f"Revised by {self.revised_by} on {self.revised_at}"


####################################################
# Towplane model
#
# Each tow plane is listed here.  the Tow plane is referenced for
# each flight in the logsheet.
#


class Towplane(models.Model):
    name = models.CharField(max_length=100)
    make = models.CharField(max_length=100, blank=True, null=True)
    model = models.CharField(max_length=100, blank=True, null=True)
    n_number = models.CharField(max_length=50)  # e.g., N-number
    photo = models.ImageField(upload_to=upload_towplane_photo, blank=True, null=True)
    photo_medium = models.ImageField(
        upload_to=upload_towplane_photo_medium,
        blank=True,
        null=True,
        help_text="150x150 square thumbnail. Auto-generated when photo is uploaded via admin.",
    )
    photo_small = models.ImageField(
        upload_to=upload_towplane_photo_small,
        blank=True,
        null=True,
        help_text="100x100 square thumbnail. Auto-generated when photo is uploaded via admin.",
    )
    is_active = models.BooleanField(default=True)
    club_owned = models.BooleanField(default=False)
    initial_hours = models.DecimalField(
        max_digits=8,
        decimal_places=1,
        default=Decimal("0.0"),
        validators=[MinValueValidator(0)],
        help_text="Starting Hobbs/total time when electronic logging began (decimal hours).",
    )
    oil_change_interval = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        default=Decimal("50.0"),
        help_text="Hours between oil changes (default 50, but configurable per aircraft).",
    )
    next_oil_change_due = models.DecimalField(
        max_digits=8,
        decimal_places=1,
        blank=True,
        null=True,
        help_text="Tach time at which next oil change is due.",
    )
    requires_100hr_inspection = models.BooleanField(
        default=False, help_text="Check if this towplane requires 100-hour inspections."
    )
    next_100hr_due = models.DecimalField(
        max_digits=8,
        decimal_places=1,
        blank=True,
        null=True,
        help_text="Tach time at which next 100-hour inspection is due.",
    )
    hourly_rental_rate = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        blank=True,
        null=True,
        help_text="Hourly rental rate for non-towing flights (sightseeing, flight reviews, retrieval, etc.) in USD per hour.",
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        status = " (Inactive)" if not self.is_active else ""
        return f"{self.name} ({self.n_number})"

    @property
    def is_grounded(self):
        return MaintenanceIssue.objects.filter(
            towplane=self, grounded=True, resolved=False
        ).exists()

    def get_active_issues(self):
        return MaintenanceIssue.objects.filter(towplane=self, resolved=False)

    @property
    def photo_url_medium(self):
        """Return URL for medium (150x150) thumbnail, falling back to full photo."""
        if self.photo_medium:
            if hasattr(self.photo_medium, "url"):
                return self.photo_medium.url
            return f"{settings.MEDIA_URL}{self.photo_medium}"
        # Fallback to full photo
        if self.photo:
            if hasattr(self.photo, "url"):
                return self.photo.url
            return f"{settings.MEDIA_URL}{self.photo}"
        return None

    @property
    def photo_url_small(self):
        """Return URL for small (100x100) thumbnail, falling back to medium, then full."""
        if self.photo_small:
            if hasattr(self.photo_small, "url"):
                return self.photo_small.url
            return f"{settings.MEDIA_URL}{self.photo_small}"
        # Fallback chain: medium -> full (reuse photo_url_medium for both)
        return self.photo_url_medium


####################################################
# Glider model
#
# All member gliders are stored in here.
# All flights in a logsheet have a glider associated with them, and it links to a glider
# in this table.  The only way to manage gliders is with the admin interface.
# The rental rates for each glider is listed here, (listed in dollars per hour)
#
class Glider(models.Model):
    make = models.CharField(max_length=100)
    model = models.CharField(max_length=100)
    # Registration (e.g. N123AB)
    n_number = models.CharField(max_length=20, unique=True)
    competition_number = models.CharField(max_length=10, blank=True)
    seats = models.PositiveIntegerField(default=2)
    photo = models.ImageField(upload_to=upload_glider_photo, blank=True, null=True)
    photo_medium = models.ImageField(
        upload_to=upload_glider_photo_medium,
        blank=True,
        null=True,
        help_text="150x150 square thumbnail. Auto-generated when photo is uploaded via admin.",
    )
    photo_small = models.ImageField(
        upload_to=upload_glider_photo_small,
        blank=True,
        null=True,
        help_text="100x100 square thumbnail. Auto-generated when photo is uploaded via admin.",
    )
    rental_rate = models.DecimalField(
        max_digits=6, decimal_places=2, blank=True, null=True
    )
    max_rental_rate = models.DecimalField(
        max_digits=6, decimal_places=2, blank=True, null=True
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Uncheck to hide this glider from flight entry dropdowns",
    )
    club_owned = models.BooleanField(default=True)
    initial_hours = models.DecimalField(
        max_digits=8,
        decimal_places=1,
        default=Decimal("0.0"),
        validators=[MinValueValidator(0)],
        help_text="Starting Hobbs/total time when electronic logging began (decimal hours).",
    )
    requires_100hr_inspection = models.BooleanField(
        default=False, help_text="Check if this glider requires 100-hour inspections."
    )
    next_100hr_due = models.DecimalField(
        max_digits=8,
        decimal_places=1,
        blank=True,
        null=True,
        help_text="Cumulative hours at which next 100-hour inspection is due.",
    )

    owners = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="gliders_owned",
        blank=True,
        help_text="Members who own this glider",
    )

    def __str__(self):
        parts = []
        if self.competition_number:
            parts.append(self.competition_number.upper())
        if self.n_number:
            parts.append(self.n_number.upper())
        if self.model:
            parts.append(self.model)
        return " / ".join(parts)

    @property
    def is_grounded(self):
        return MaintenanceIssue.objects.filter(
            glider=self, grounded=True, resolved=False
        ).exists()

    def get_active_issues(self):
        return MaintenanceIssue.objects.filter(glider=self, resolved=False)

    @property
    def photo_url_medium(self):
        """Return URL for medium (150x150) thumbnail, falling back to full photo."""
        if self.photo_medium:
            if hasattr(self.photo_medium, "url"):
                return self.photo_medium.url
            return f"{settings.MEDIA_URL}{self.photo_medium}"
        # Fallback to full photo
        if self.photo:
            if hasattr(self.photo, "url"):
                return self.photo.url
            return f"{settings.MEDIA_URL}{self.photo}"
        return None

    @property
    def photo_url_small(self):
        """Return URL for small (100x100) thumbnail, falling back to medium, then full."""
        if self.photo_small:
            if hasattr(self.photo_small, "url"):
                return self.photo_small.url
            return f"{settings.MEDIA_URL}{self.photo_small}"
        # Fallback chain: medium -> full (reuse photo_url_medium for both)
        return self.photo_url_medium


####################################################
# Airfield model
#
# The Logsheet model refers to the Airfields, where we keep a list
# of all the airfields that we can operate out of.  The only
# way to manage the Airfields is through the admin interface.
#
class Airfield(models.Model):
    identifier = models.CharField(max_length=10, unique=True)  # e.g., KFRR
    # e.g., Front Royal Warren County Airport
    name = models.CharField(max_length=100)
    photo = models.ImageField(upload_to=upload_airfield_photo, blank=True, null=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.identifier} – {self.name}"


####################################################
# Logsheet model
#
# Each logsheet has some particular information associated with it, like
# what day the operations happened, what airfield these operations happened at.
# Also, we record who was scheduled and participated for the duty on this day.
# that includes the duty officer, instructor, tow pilots, and any other staff
# associated with this day's flight ops.
#


class Logsheet(models.Model):
    log_date = models.DateField()
    airfield = models.ForeignKey(Airfield, on_delete=models.PROTECT)
    created_by = models.ForeignKey(Member, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    finalized = models.BooleanField(default=False)

    duty_officer = models.ForeignKey(
        Member,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="log_duty_officer",
        limit_choices_to={"duty_officer": True},
    )
    assistant_duty_officer = models.ForeignKey(
        Member,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="log_assistant_duty_officer",
        limit_choices_to={"assistant_duty_officer": True},
    )
    duty_instructor = models.ForeignKey(
        Member,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="log_duty_instructor",
        limit_choices_to={"instructor": True},
    )
    surge_instructor = models.ForeignKey(
        Member,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="log_surge_instructor",
        limit_choices_to={"instructor": True},
    )
    tow_pilot = models.ForeignKey(
        Member,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="log_tow_pilot",
        limit_choices_to={"towpilot": True},
    )
    surge_tow_pilot = models.ForeignKey(
        Member,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="log_surge_tow_pilot",
        limit_choices_to={"towpilot": True},
    )
    default_towplane = models.ForeignKey(
        Towplane, on_delete=models.SET_NULL, null=True, blank=True
    )

    class Meta:
        unique_together = ("log_date", "airfield")

    def __str__(self):
        return f"{self.log_date} @ {self.airfield}"

    def save(self, *args, **kwargs):
        from decimal import Decimal

        from logsheet.models import MaintenanceIssue

        is_new = self.pk is None
        # Fetch previous finalized state if updating
        if not is_new:
            old = Logsheet.objects.get(pk=self.pk)
            was_finalized = old.finalized
        else:
            was_finalized = False
        super().save(*args, **kwargs)
        # Only run automation if just finalized
        if not was_finalized and self.finalized:
            # --- Towplane oil change and 100hr checks ---
            for closeout in self.towplane_closeouts.all():
                towplane = closeout.towplane
                stop_tach = closeout.end_tach
                # Oil change logic
                if towplane.next_oil_change_due:
                    due = towplane.next_oil_change_due
                    interval = towplane.oil_change_interval or Decimal("50.0")
                    if stop_tach is not None:
                        hours_to_due = due - stop_tach
                        if hours_to_due <= 10 and hours_to_due > 0:
                            MaintenanceIssue.objects.get_or_create(
                                towplane=towplane,
                                logsheet=self,
                                description=f"Towplane oil change due in {hours_to_due:.1f} hours (at {due}).",
                                grounded=False,
                                resolved=False,
                            )
                        elif hours_to_due <= 0:
                            MaintenanceIssue.objects.get_or_create(
                                towplane=towplane,
                                logsheet=self,
                                description=f"Towplane oil change OVERDUE (due at {due}, now {stop_tach}).",
                                grounded=True,
                                resolved=False,
                            )
                # 100hr logic
                if towplane.requires_100hr_inspection and towplane.next_100hr_due:
                    due = towplane.next_100hr_due
                    if stop_tach is not None:
                        hours_to_due = due - stop_tach
                        if hours_to_due <= 10 and hours_to_due > 0:
                            MaintenanceIssue.objects.get_or_create(
                                towplane=towplane,
                                logsheet=self,
                                description=f"Towplane 100-hour inspection due in {hours_to_due:.1f} hours (at {due}).",
                                grounded=False,
                                resolved=False,
                            )
                        elif hours_to_due <= 0:
                            MaintenanceIssue.objects.get_or_create(
                                towplane=towplane,
                                logsheet=self,
                                description=f"Towplane 100-hour inspection OVERDUE (due at {due}, now {stop_tach}).",
                                grounded=True,
                                resolved=False,
                            )
            # --- Glider 100hr checks ---
            for glider in self.flights.values_list("glider", flat=True).distinct():
                if not glider:
                    continue
                g = Glider.objects.filter(pk=glider).first()
                if not g or not g.requires_100hr_inspection or not g.next_100hr_due:
                    continue
                # Calculate cumulative hours for this glider up to this logsheet
                # (Assume initial_hours + sum of all durations for this glider)
                from django.db.models import DurationField, ExpressionWrapper, F, Sum

                flights = g.flights_as_pilot.all().filter(
                    logsheet__log_date__lte=self.log_date
                )
                total_seconds = (
                    flights.aggregate(
                        s=Sum(
                            ExpressionWrapper(
                                F("duration"), output_field=DurationField()
                            )
                        )
                    )["s"].total_seconds()
                    if flights.exists()
                    else 0
                )
                cum_hours = (g.initial_hours or Decimal("0.0")) + Decimal(
                    total_seconds or 0
                ) / Decimal(3600)
                due = g.next_100hr_due
                hours_to_due = due - cum_hours
                if hours_to_due <= 10 and hours_to_due > 0:
                    MaintenanceIssue.objects.get_or_create(
                        glider=g,
                        logsheet=self,
                        description=f"Glider 100-hour inspection due in {hours_to_due:.1f} hours (at {due}).",
                        grounded=False,
                        resolved=False,
                    )
                elif hours_to_due <= 0:
                    MaintenanceIssue.objects.get_or_create(
                        glider=g,
                        logsheet=self,
                        description=f"Glider 100-hour inspection OVERDUE (due at {due}, now {cum_hours:.1f}).",
                        grounded=True,
                        resolved=False,
                    )

            # --- Notify maintenance officers about all unresolved issues on this logsheet ---
            # This handles issues created before finalization that didn't send notifications
            from notifications.models import Notification

            unresolved_issues = MaintenanceIssue.objects.filter(
                logsheet=self, resolved=False
            ).select_related("glider", "towplane")

            for issue in unresolved_issues:
                # Get the aircraft meisters
                if issue.glider:
                    meisters = issue.glider.aircraftmeister_set.select_related(
                        "member"
                    ).all()
                elif issue.towplane:
                    meisters = issue.towplane.aircraftmeister_set.select_related(
                        "member"
                    ).all()
                else:
                    meisters = []

                if not meisters:
                    continue

                # Create notification message
                message = f"Maintenance issue reported for {issue.glider or issue.towplane}: {issue.description[:100]}"
                try:
                    from django.urls import reverse

                    url = reverse("logsheet:maintenance_issues")
                except Exception:
                    url = None

                # Notify each meister (with deduplication)
                for meister in meisters:
                    try:
                        existing = Notification.objects.filter(
                            user=meister.member, dismissed=False, message=message
                        )
                        if not existing.exists():
                            Notification.objects.create(
                                user=meister.member, message=message, url=url
                            )
                    except Exception as e:
                        import logging

                        logger = logging.getLogger(__name__)
                        logger.exception(
                            "Failed to create maintenance notification for meister %s: %s",
                            meister.member.pk if meister and meister.member else None,
                            str(e),
                        )


####################################################
# TowplaneChargeScheme model
#
# Defines a charging scheme for a specific towplane.
# Supports both simple per-altitude pricing and complex tiered pricing with hookup fees.
#


class TowplaneChargeScheme(models.Model):
    """
    Defines a charging scheme for a specific towplane.

    Supports both simple per-altitude pricing and complex tiered pricing with hookup fees.
    """

    towplane = models.OneToOneField(
        "Towplane",
        on_delete=models.CASCADE,
        related_name="charge_scheme",
        help_text="The towplane this charging scheme applies to",
    )

    name = models.CharField(
        max_length=100,
        help_text="Descriptive name for this charging scheme (e.g., 'Pawnee Standard Rates')",
    )

    hookup_fee = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Fixed fee charged for any tow, regardless of altitude ($0 if none)",
    )

    is_active = models.BooleanField(
        default=True,
        help_text="If unchecked, falls back to global TowRate system",
        db_index=True,
    )

    description = models.TextField(
        blank=True, help_text="Optional description of this pricing scheme"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["towplane__name"]
        verbose_name = "Towplane Charge Scheme"
        verbose_name_plural = "Towplane Charge Schemes"

    def __str__(self):
        return f"{self.towplane.name} - {self.name}"

    def calculate_tow_cost(self, altitude_feet):
        """
        Calculate the tow cost for the given altitude using this scheme's tiers.

        Args:
            altitude_feet (int): Release altitude in feet

        Returns:
            Decimal: Total tow cost including hookup fee and tiered charges
        """
        if not self.is_active or altitude_feet is None:
            return None

        total_cost = self.hookup_fee

        # Apply tiered pricing in order, cache active tiers to avoid N+1 queries
        if not hasattr(self, "_active_charge_tiers"):
            self._active_charge_tiers = list(
                self.charge_tiers.filter(is_active=True).order_by("altitude_start")
            )
        for tier in self._active_charge_tiers:
            # Calculate altitude range for this tier
            tier_start = tier.altitude_start
            tier_end = tier.altitude_end if tier.altitude_end else float("inf")

            # Skip if the flight altitude doesn't reach this tier
            if altitude_feet <= tier_start:
                continue

            # Calculate the actual altitude range that falls within this tier
            altitude_start_in_tier = max(tier_start, 0)
            altitude_end_in_tier = min(altitude_feet, tier_end)

            # Only charge if there's actual altitude in this tier
            if altitude_end_in_tier > altitude_start_in_tier:
                altitude_in_tier = altitude_end_in_tier - altitude_start_in_tier
                tier_cost = tier.calculate_cost(altitude_in_tier)
                total_cost += tier_cost

        return total_cost.quantize(Decimal("0.01"))


####################################################
# TowplaneChargeTier model
#
# Represents a pricing tier within a towplane charge scheme.
# Examples:
# - First 1000ft: $10 flat rate
# - 1001-2000ft: $5 per 1000ft
# - Above 2000ft: $3 per 1000ft
#


class TowplaneChargeTier(models.Model):
    """
    Represents a pricing tier within a towplane charge scheme.

    Examples:
    - First 1000ft: $10 flat rate
    - 1001-2000ft: $5 per 1000ft
    - Above 2000ft: $3 per 1000ft
    """

    RATE_TYPE_CHOICES = [
        ("flat", "Flat Rate (charge once for entire tier)"),
        ("per_1000ft", "Per 1000 feet (charge per 1000ft increment)"),
        ("per_100ft", "Per 100 feet (charge per 100ft increment)"),
    ]

    charge_scheme = models.ForeignKey(
        TowplaneChargeScheme,
        on_delete=models.CASCADE,
        related_name="charge_tiers",
        help_text="The charge scheme this tier belongs to",
    )

    altitude_start = models.PositiveIntegerField(
        help_text="Starting altitude for this tier (feet, inclusive)",
        validators=[MinValueValidator(0)],
    )

    altitude_end = models.PositiveIntegerField(
        blank=True,
        null=True,
        help_text="Ending altitude for this tier (feet, exclusive). Leave blank for unlimited.",
    )

    rate_type = models.CharField(
        max_length=20,
        choices=RATE_TYPE_CHOICES,
        default="per_1000ft",
        help_text="How to calculate charges for this altitude range",
    )

    rate_amount = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Rate amount in USD (interpretation depends on rate_type)",
    )

    is_active = models.BooleanField(
        default=True,
        help_text="If unchecked, this tier is ignored in calculations",
        db_index=True,
    )

    description = models.CharField(
        max_length=200,
        blank=True,
        help_text="Optional description (e.g., 'Base tow to pattern altitude')",
    )

    class Meta:
        ordering = ["charge_scheme", "altitude_start"]
        verbose_name = "Towplane Charge Tier"
        verbose_name_plural = "Towplane Charge Tiers"
        unique_together = ["charge_scheme", "altitude_start"]

    def __str__(self):
        end_str = f"-{self.altitude_end}" if self.altitude_end else "+"
        return f"{self.charge_scheme.towplane.name}: {self.altitude_start}{end_str}ft @ ${self.rate_amount} {self.rate_type}"

    def clean(self):
        """Validate tier altitude ranges and prevent overlapping tiers."""
        from django.core.exceptions import ValidationError

        if self.altitude_end is not None and self.altitude_end <= self.altitude_start:
            raise ValidationError("End altitude must be greater than start altitude")

        # Check for overlapping tiers within the same charge_scheme
        if self.charge_scheme_id:
            # Exclude self from the queryset if already saved
            overlapping_qs = self.charge_scheme.charge_tiers.exclude(pk=self.pk)
            # Treat None altitude_end as "open-ended" (infinity)
            this_start = self.altitude_start
            this_end = (
                self.altitude_end if self.altitude_end is not None else float("inf")
            )
            for tier in overlapping_qs:
                other_start = tier.altitude_start
                other_end = (
                    tier.altitude_end if tier.altitude_end is not None else float("inf")
                )
                # Overlap exists if ranges intersect
                if not (this_end <= other_start or this_start >= other_end):
                    raise ValidationError(
                        f"Tier altitude range {this_start}-{self.altitude_end or '∞'}ft overlaps with existing tier {other_start}-{tier.altitude_end or '∞'}ft"
                    )

    def calculate_cost(self, altitude_feet):
        """
        Calculate the cost for the given altitude within this tier.

        Args:
            altitude_feet (int): Altitude covered by this tier

        Returns:
            Decimal: Cost for this tier
        """
        if not self.is_active or altitude_feet <= 0:
            return Decimal("0.00")

        if self.rate_type == "flat":
            # Flat rate - charge once regardless of altitude within tier
            return self.rate_amount
        elif self.rate_type == "per_1000ft":
            # Per 1000ft - charge for each 1000ft increment
            increments = (altitude_feet + 999) // 1000  # Round up
            return self.rate_amount * increments
        elif self.rate_type == "per_100ft":
            # Per 100ft - charge for each 100ft increment
            increments = (altitude_feet + 99) // 100  # Round up
            return self.rate_amount * increments

        return Decimal("0.00")


####################################################
# LogsheetPayment model
#
# The methods that each member who paid for flights show up here.
# This is based on what is in the logsheet.  Sometimes a pilot can
# fly multiple times, so this is where the costs for the sum of those
# flights are marked for payment.
#


class LogsheetPayment(models.Model):
    logsheet = models.ForeignKey(
        Logsheet, on_delete=models.CASCADE, related_name="payments"
    )
    member = models.ForeignKey(
        Member, on_delete=models.CASCADE, related_name="logsheet_payments"
    )
    payment_method = models.CharField(
        max_length=10,
        choices=[
            ("account", "On Account"),
            ("check", "Check"),
            ("zelle", "Zelle"),
            ("cash", "Cash"),
        ],
        null=True,
        blank=True,
    )
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        unique_together = ("logsheet", "member")

    def __str__(self):
        return f"{self.member} - {self.logsheet.log_date} ({self.payment_method or 'Unpaid'})"


####################################################
# LogsheetCloseout model
#
# When the duty officer is ready to finalize a logsheet, there's one closeout page
# that allows him to write up safety issues, equipment issues and a summary of the operations
# This used to be done in an email, but the email gets lost to time.  Why not keep it
# in our record for future generations to review, without having to trundle through the email
# archives?
#


class LogsheetCloseout(models.Model):
    logsheet = models.OneToOneField(
        Logsheet, on_delete=models.CASCADE, related_name="closeout"
    )
    safety_issues = HTMLField(blank=True)
    equipment_issues = HTMLField(blank=True)
    operations_summary = HTMLField(blank=True)


####################################################
# TowplaneCloseout model
#
# This model tracks end-of-day towplane operations for each logsheet.
# Includes starting and ending tachometer readings, total tach time,
# fuel added during operations, and any operational notes.
#
# Fields:
# - logsheet: The associated logsheet for the closeout.
# - towplane: The towplane being closed out.
# - start_tach: Starting tach reading at beginning of day.
# - end_tach: Ending tach reading at end of day.
# - tach_time: Total flight time for the towplane for the day.
# - fuel_added: Amount of fuel added to the towplane during the day.
# - notes: Any operational comments or anomalies.
#
# Methods:
# - __str__: Returns a string showing the towplane and date.
#


class TowplaneCloseout(models.Model):
    logsheet = models.ForeignKey(
        Logsheet, on_delete=models.CASCADE, related_name="towplane_closeouts"
    )
    towplane = models.ForeignKey(Towplane, on_delete=models.CASCADE)
    start_tach = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True
    )
    end_tach = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True
    )
    tach_time = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True
    )
    fuel_added = models.DecimalField(
        max_digits=5, decimal_places=1, null=True, blank=True
    )
    rental_hours_chargeable = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        blank=True,
        null=True,
        help_text="Hours of towplane use to be charged as rental (non-towing flights like sightseeing, flight reviews, retrieval).",
    )
    rental_charged_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Member to be charged for towplane rental time (if any).",
    )
    notes = HTMLField(blank=True)

    class Meta:
        unique_together = ("logsheet", "towplane")
        indexes = [
            models.Index(fields=["towplane", "logsheet"]),
        ]

    @property
    def rental_cost(self):
        """
        Calculate rental cost for non-towing towplane usage.

        Performance note:
        Accesses self.towplane.hourly_rental_rate, which will trigger a database query
        if the towplane relation is not prefetched. For best performance, especially in
        financial views or loops, use select_related('towplane') when querying
        TowplaneCloseout objects.
        """
        if (
            self.rental_hours_chargeable is None
            or self.rental_hours_chargeable <= 0
            or not self.towplane.hourly_rental_rate
        ):
            return None
        return self.rental_hours_chargeable * self.towplane.hourly_rental_rate

    @property
    def rental_cost_display(self):
        """Display formatted rental cost."""
        cost = self.rental_cost
        return f"${cost:.2f}" if cost is not None else "—"

    def __str__(self):
        return f"{self.towplane.n_number} on {self.logsheet.log_date}"


####################################################
# MaintenanceIssue model
#
# This model tracks reported maintenance issues for gliders or towplanes.
# Issues can be open or resolved, and can optionally ground an aircraft.
# Each issue is linked to a logsheet if reported during operations.
#
# Fields:
# - glider / towplane: The affected aircraft.
# - description: Text description of the problem.
# - grounded: Whether the issue grounds the aircraft.
# - resolved: Whether the issue has been addressed.
# - resolution_notes: How the issue was resolved.
# - reported_by / resolved_by: Members who reported or resolved the issue.
# - logsheet: Optional link to the logsheet where it was reported.
#
# Methods:
# - __str__: Returns a summary of the issue.
# - can_be_resolved_by(user): Checks if a given user can resolve the issue.
#


class MaintenanceIssue(models.Model):
    def save(self, *args, **kwargs):
        from django.utils import timezone

        # Set report_date to logsheet.log_date if available, else today
        if self.logsheet and self.logsheet.log_date:
            self.report_date = self.logsheet.log_date
        elif not self.report_date:
            self.report_date = timezone.now().date()
        super().save(*args, **kwargs)

    glider = models.ForeignKey(
        "logsheet.Glider", null=True, blank=True, on_delete=models.CASCADE
    )
    towplane = models.ForeignKey(
        "logsheet.Towplane", null=True, blank=True, on_delete=models.CASCADE
    )
    reported_by = models.ForeignKey(Member, on_delete=models.SET_NULL, null=True)
    report_date = models.DateField()
    logsheet = models.ForeignKey(
        "Logsheet",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="maintenance_issues",
    )

    description = models.TextField()
    grounded = models.BooleanField(default=False)
    resolved = models.BooleanField(default=False)
    resolution_notes = models.TextField(blank=True)
    resolved_by = models.ForeignKey(
        Member,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resolved_maintenance",
    )
    resolved_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["-report_date"]

    def __str__(self):
        aircraft = self.glider or self.towplane
        label = f"{aircraft}"
        return f"{label} - {'Grounded' if self.grounded else 'Open'} - {self.description[:40]}"

    def can_be_resolved_by(self, user):
        if user.is_superuser:
            return True
        if self.glider and user.id in self.glider.aircraftmeister_set.values_list(
            "member_id", flat=True
        ):
            return True
        if self.towplane and user.id in self.towplane.aircraftmeister_set.values_list(
            "member_id", flat=True
        ):
            return True
        return False


class DeadlineType(models.TextChoices):
    ANNUAL = "annual", "Annual Inspection"
    CONDITION = "condition", "Condition Inspection"
    PARACHUTE = "parachute", "Parachute Repack"
    TRANSPONDER = "transponder", "Transponder Inspection"
    LETTER = "letter", "Program Letter"


DEADLINE_TYPES = [
    ("annual", "Annual Inspection"),
    ("condition", "Condition Inspection"),
    ("parachute", "Parachute Repack"),
    ("transponder", "Transponder Inspection"),
    ("letter", "Program Letter"),
]

####################################################
# MaintenanceDeadline model
#
# Tracks scheduled maintenance deadlines for gliders or towplanes.
# Each deadline represents a recurring inspection or repack requirement.
#
# Fields:
# - glider / towplane: The affected aircraft.
# - description: Type of deadline (annual, transponder, parachute, etc.).
# - due_date: When the deadline is due.
#
# Methods:
# - __str__: Returns a readable summary of the upcoming deadline.
#

DEADLINE_TYPES = DeadlineType.choices


class MaintenanceDeadline(models.Model):
    glider = models.ForeignKey(Glider, on_delete=models.CASCADE, blank=True, null=True)
    towplane = models.ForeignKey(
        Towplane, on_delete=models.CASCADE, blank=True, null=True
    )
    description = models.CharField(max_length=32, choices=DeadlineType)
    due_date = models.DateField()

    @property
    def description_label(self) -> str:
        # Pylance-friendly label without relying on Django’s dynamic get_*_display
        try:
            return DeadlineType(self.description).label
        except ValueError:
            return self.description  # fallback if legacy/unknown value sneaks in

    def __str__(self):
        aircraft = self.glider or self.towplane
        return f"{aircraft} - {self.description_label} due {self.due_date:%Y-%m-%d}"


####################################################
# AircraftMeister model
#
# Associates a Member with responsibility for a glider or towplane.
# Aircraft Meisters are authorized to resolve maintenance issues
# on the aircraft they are assigned to.
#
# Fields:
# - glider / towplane: The aircraft they oversee.
# - member: The assigned member (meister).
#
# Methods:
# - __str__: Returns the member and aircraft they oversee.
#


class AircraftMeister(models.Model):
    glider = models.ForeignKey(Glider, null=True, blank=True, on_delete=models.CASCADE)
    towplane = models.ForeignKey(
        Towplane, null=True, blank=True, on_delete=models.CASCADE
    )
    member = models.ForeignKey(Member, on_delete=models.CASCADE)

    def __str__(self):
        aircraft = self.glider or self.towplane
        return f"{self.member} – {aircraft}"


####################################################
# MemberCharge model
#
# Records miscellaneous charges applied to members for merchandise,
# services, or fees not captured by flight costs.
#
# Issue #66: Aerotow retrieve fees (tach time charges)
# Issue #413: Miscellaneous charges (t-shirts, logbooks, etc.)
#
# Fields:
# - member: The member being charged.
# - chargeable_item: Reference to the ChargeableItem catalog.
# - quantity: Amount purchased (supports decimals for tach time).
# - unit_price: Snapshot of price at time of charge (immutable).
# - total_price: Computed total (quantity × unit_price).
# - date: Date the charge was applied.
# - logsheet: Optional link to logsheet (for finalization logic).
# - notes: Optional notes about the charge.
# - entered_by: Member who entered the charge.
#
# Methods:
# - save: Auto-calculates total_price on save.
# - __str__: Returns a readable summary of the charge.
#


class MemberCharge(models.Model):
    member = models.ForeignKey(
        Member,
        on_delete=models.CASCADE,
        related_name="misc_charges",
        help_text="Member being charged",
    )
    chargeable_item = models.ForeignKey(
        "siteconfig.ChargeableItem",
        on_delete=models.PROTECT,
        help_text="Item or service being charged",
    )
    quantity = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal("1.00"),
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text="Quantity (supports decimals for tach time, e.g., 1.8 hours)",
    )
    unit_price = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Price per unit at time of charge (snapshot, won't change if catalog price updates)",
    )
    total_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Total charge (quantity × unit_price)",
    )
    date = models.DateField(
        default=date.today,
        help_text="Date the charge was applied",
    )
    logsheet = models.ForeignKey(
        "Logsheet",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="member_charges",
        help_text="Optional link to logsheet (charges tied to finalized logsheets are locked)",
    )
    notes = models.TextField(
        blank=True,
        help_text="Optional notes about this charge",
    )
    entered_by = models.ForeignKey(
        Member,
        on_delete=models.SET_NULL,
        null=True,
        related_name="charges_entered",
        help_text="Member who entered this charge",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Member Charge"
        verbose_name_plural = "Member Charges"
        ordering = ["-date", "-created_at"]
        indexes = [
            models.Index(fields=["member", "date"]),
            models.Index(fields=["logsheet"]),
        ]

    def clean(self):
        """Validate that either unit_price is provided or chargeable_item is set."""
        from django.core.exceptions import ValidationError

        if self.unit_price is None and not self.chargeable_item_id:
            raise ValidationError(
                "Either unit_price must be provided or chargeable_item must be set."
            )

    def save(self, *args, **kwargs):
        """Auto-calculate total_price and snapshot unit_price if not set."""
        # Snapshot the price from the catalog item if not already set
        if self.unit_price is None and self.chargeable_item:
            self.unit_price = self.chargeable_item.price

        # Calculate total
        if self.quantity and self.unit_price:
            self.total_price = (self.quantity * self.unit_price).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        else:
            self.total_price = Decimal("0.00")

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.member} - {self.chargeable_item.name} (${self.total_price})"

    @property
    def is_locked(self):
        """Charges tied to finalized logsheets cannot be edited."""
        return self.logsheet and self.logsheet.finalized
