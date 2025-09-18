# from .models import Towplane, Airfield  # Adjust import paths as needed
from django.db import models
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timedelta, date
from tinymce.models import HTMLField
from django.conf import settings
from members.models import Member
from django.core.validators import MinValueValidator


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
    logsheet = models.ForeignKey(
        "Logsheet", on_delete=models.CASCADE, related_name="flights")
    launch_time = models.TimeField(blank=True, null=True)
    landing_time = models.TimeField(blank=True, null=True)
    pilot = models.ForeignKey(
        "members.Member", on_delete=models.SET_NULL, null=True, related_name="flights_as_pilot")
    instructor = models.ForeignKey("members.Member", on_delete=models.SET_NULL,
                                   null=True, blank=True, related_name="flights_as_instructor")
    glider = models.ForeignKey(
        "logsheet.Glider", on_delete=models.SET_NULL, null=True)
    tow_pilot = models.ForeignKey("members.Member", on_delete=models.SET_NULL,
                                  null=True, blank=True, related_name="flights_as_tow_pilot")
    towplane = models.ForeignKey(
        "Towplane", on_delete=models.SET_NULL, null=True, blank=True)
    duration = models.DurationField(blank=True, null=True)
    passenger = models.ForeignKey(Member, on_delete=models.SET_NULL,
                                  null=True, blank=True, related_name="flights_as_passenger")

    # Guest name fallbacks (for legacy import)
    guest_pilot_name = models.CharField(max_length=100, blank=True, null=True)
    guest_instructor_name = models.CharField(
        max_length=100, blank=True, null=True)
    guest_towpilot_name = models.CharField(
        max_length=100, blank=True, null=True)

    # Legacy name tracking for post-import cleanup or debug
    passenger_name = models.CharField(
        max_length=100, blank=True, help_text="Name of passenger if not a member")
    legacy_pilot_name = models.CharField(max_length=100, blank=True, null=True)
    legacy_instructor_name = models.CharField(
        max_length=100, blank=True, null=True)
    legacy_passenger_name = models.CharField(
        max_length=100, blank=True, null=True)
    legacy_towpilot_name = models.CharField(
        max_length=100, blank=True, null=True)

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
    airfield = models.ForeignKey(
        "Airfield", on_delete=models.PROTECT, null=True)

    flight_type = models.CharField(max_length=50)  # dual, solo, intro, etc.
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    RELEASE_ALTITUDE_CHOICES = [(i, f"{i} ft") for i in range(0, 7100, 100)]

    release_altitude = models.IntegerField(
        choices=RELEASE_ALTITUDE_CHOICES,
        blank=True,
        null=True,
        help_text="Release altitude in feet (0–7000 in 100ft steps)"
    )
    tow_cost_actual = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True)
    rental_cost_actual = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True)

    def is_incomplete(self):
        return (
            self.landing_time is not None and (
                self.release_altitude is None or
                self.towplane is None or
                self.tow_pilot is None
            )
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
        if self.release_altitude is None:
            return None
        return (
            TowRate.objects
            .filter(altitude__lte=self.release_altitude)
            .order_by("-altitude")
            .values_list("price", flat=True)
            .first()
        )

    @property
    def rental_cost_calculated(self):
        if not self.glider or not self.duration:
            return None
        if not self.glider.rental_rate:
            return Decimal("0.00")
        hours = Decimal(self.duration.total_seconds()) / Decimal(3600)
        return Decimal(str(self.glider.rental_rate)) * hours

    @property
    def tow_cost(self):
        if self.release_altitude is None:
            return None
        return (
            TowRate.objects
            .filter(altitude__lte=self.release_altitude)
            .order_by("-altitude")
            .values_list("price", flat=True)
            .first()
        )

    @property
    def tow_cost_display(self):
        cost = self.tow_cost
        return f"${cost:.2f}" if cost else "—"

    @property
    def rental_cost(self):
        if not self.glider or not self.duration:
            return None
        if not self.glider.rental_rate:
            return Decimal("0.00")

        hours = Decimal(self.duration.total_seconds()) / Decimal("3600")
        rate = Decimal(str(self.glider.rental_rate))
        cost = rate * hours

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
                if (launch_dt - land_dt).total_seconds() < 16 * 3600:  # < 16 hours difference
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
        related_name="shared_flights"
    )

    split_type = models.CharField(
        max_length=10,
        choices=[
            ("even", "50/50"),
            ("tow", "Tow Only"),
            ("rental", "Rental Only"),
            ("full", "Full Cost")
        ],
        null=True,
        blank=True
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
        "Logsheet", on_delete=models.CASCADE, related_name="revisions")
    revised_by = models.ForeignKey(
        Member, on_delete=models.SET_NULL, null=True)
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
    photo = models.ImageField(
        upload_to="towplane_photos/", blank=True, null=True)
    is_active = models.BooleanField(default=True)
    club_owned = models.BooleanField(default=False)
    initial_hours = models.DecimalField(
        max_digits=8, decimal_places=1, default=Decimal("0.0"),
        validators=[MinValueValidator(0)],
        help_text="Starting Hobbs/total time when electronic logging began (decimal hours).",
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        status = " (Inactive)" if not self.is_active else ""
        return f"{self.name} ({self.n_number})"

    @property
    def is_grounded(self):
        return MaintenanceIssue.objects.filter(
            towplane=self,
            grounded=True,
            resolved=False
        ).exists()

    def get_active_issues(self):
        return MaintenanceIssue.objects.filter(
            towplane=self,
            resolved=False
        )


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
    photo = models.ImageField(
        upload_to="glider_photos/", blank=True, null=True)
    rental_rate = models.DecimalField(
        max_digits=6, decimal_places=2, blank=True, null=True)
    max_rental_rate = models.DecimalField(
        max_digits=6, decimal_places=2, blank=True, null=True)
    is_active = models.BooleanField(
        default=True,
        help_text="Uncheck to hide this glider from flight entry dropdowns"
    )
    club_owned = models.BooleanField(default=True)
    initial_hours = models.DecimalField(
        max_digits=8, decimal_places=1, default=Decimal("0.0"),
        validators=[MinValueValidator(0)],
        help_text="Starting Hobbs/total time when electronic logging began (decimal hours).",
    )

    owners = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="gliders_owned",
        blank=True,
        help_text="Members who own this glider"
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
            glider=self,
            grounded=True,
            resolved=False
        ).exists()

    def get_active_issues(self):
        return MaintenanceIssue.objects.filter(
            glider=self,
            resolved=False
        )


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
    photo = models.ImageField(
        upload_to='airfield_photos/', blank=True, null=True)
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

    duty_officer = models.ForeignKey(Member, on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name="log_duty_officer", limit_choices_to={"duty_officer": True})
    assistant_duty_officer = models.ForeignKey(Member, on_delete=models.SET_NULL, null=True, blank=True,
                                               related_name="log_assistant_duty_officer", limit_choices_to={"assistant_duty_officer": True})
    duty_instructor = models.ForeignKey(Member, on_delete=models.SET_NULL, null=True,
                                        blank=True, related_name="log_duty_instructor", limit_choices_to={"instructor": True})
    surge_instructor = models.ForeignKey(Member, on_delete=models.SET_NULL, null=True,
                                         blank=True, related_name="log_surge_instructor", limit_choices_to={"instructor": True})
    tow_pilot = models.ForeignKey(Member, on_delete=models.SET_NULL, null=True,
                                  blank=True, related_name="log_tow_pilot", limit_choices_to={"towpilot": True})
    surge_tow_pilot = models.ForeignKey(Member, on_delete=models.SET_NULL, null=True,
                                        blank=True, related_name="log_surge_tow_pilot", limit_choices_to={"towpilot": True})
    default_towplane = models.ForeignKey(
        Towplane, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        unique_together = ("log_date", "airfield")

    def __str__(self):
        return f"{self.log_date} @ {self.airfield}"


####################################################
# TowRate model
#
# The price for an aerotow to a particular height are stored here
# All tow heights are all the same price, mo matter the towplane.
# (This should probably be changed later)
#
class TowRate(models.Model):
    altitude = models.PositiveIntegerField(
        help_text="Release altitude in feet (e.g. 2000)")
    price = models.DecimalField(
        max_digits=6, decimal_places=2, help_text="Price in USD")

    class Meta:
        ordering = ['altitude']

    def __str__(self):
        return f"{self.altitude} ft – ${self.price:.2f}"

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
            ("cash", "Cash")
        ],
        null=True,
        blank=True
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
        Logsheet, on_delete=models.CASCADE, related_name="closeout")
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
        Logsheet, on_delete=models.CASCADE, related_name="towplane_closeouts")
    towplane = models.ForeignKey(Towplane, on_delete=models.CASCADE)
    start_tach = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True)
    end_tach = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True)
    tach_time = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True)
    fuel_added = models.DecimalField(
        max_digits=5, decimal_places=1, null=True, blank=True)
    notes = HTMLField(blank=True)

    class Meta:
        unique_together = ("logsheet", "towplane")

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
        "logsheet.Glider", null=True, blank=True, on_delete=models.CASCADE)
    towplane = models.ForeignKey(
        "logsheet.Towplane", null=True, blank=True, on_delete=models.CASCADE)
    reported_by = models.ForeignKey(
        Member, on_delete=models.SET_NULL, null=True)
    report_date = models.DateField()
    logsheet = models.ForeignKey("Logsheet", on_delete=models.SET_NULL,
                                 null=True, blank=True, related_name="maintenance_issues")

    description = models.TextField()
    grounded = models.BooleanField(default=False)
    resolved = models.BooleanField(default=False)
    resolution_notes = models.TextField(blank=True)
    resolved_by = models.ForeignKey(
        Member, on_delete=models.SET_NULL, null=True, blank=True, related_name="resolved_maintenance")
    resolved_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ['-report_date']

    def __str__(self):
        aircraft = self.glider or self.towplane
        label = f"{aircraft}"
        return f"{label} - {'Grounded' if self.grounded else 'Open'} - {self.description[:40]}"

    def can_be_resolved_by(self, user):
        if user.is_superuser:
            return True
        if self.glider and user.id in self.glider.aircraftmeister_set.values_list('member_id', flat=True):
            return True
        if self.towplane and user.id in self.towplane.aircraftmeister_set.values_list('member_id', flat=True):
            return True
        return False


class DeadlineType(models.TextChoices):
    ANNUAL = "annual",      "Annual Inspection"
    CONDITION = "condition",   "Condition Inspection"
    PARACHUTE = "parachute",   "Parachute Repack"
    TRANSPONDER = "transponder", "Transponder Inspection"
    LETTER = "letter",      "Program Letter"


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
    glider = models.ForeignKey(
        Glider, on_delete=models.CASCADE, blank=True, null=True)
    towplane = models.ForeignKey(
        Towplane, on_delete=models.CASCADE, blank=True, null=True)
    description = models.CharField(max_length=32, choices=DeadlineType.choices)
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
    glider = models.ForeignKey(
        Glider, null=True, blank=True, on_delete=models.CASCADE)
    towplane = models.ForeignKey(
        Towplane, null=True, blank=True, on_delete=models.CASCADE)
    member = models.ForeignKey(Member, on_delete=models.CASCADE)

    def __str__(self):
        aircraft = self.glider or self.towplane
        return f"{self.member} – {aircraft}"
