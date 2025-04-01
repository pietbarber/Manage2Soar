from django.db import models
from members.models import Member
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timedelta, date

class Flight(models.Model):
    logsheet = models.ForeignKey("Logsheet", on_delete=models.CASCADE, related_name="flights")
    launch_time = models.TimeField()
    landing_time = models.TimeField(blank=True, null=True)
    pilot = models.ForeignKey("members.Member", on_delete=models.SET_NULL, null=True, related_name="flights_as_pilot")
    instructor = models.ForeignKey("members.Member", on_delete=models.SET_NULL, null=True, blank=True, related_name="flights_as_instructor")
    glider = models.ForeignKey("logsheet.Glider", on_delete=models.SET_NULL, null=True)
    tow_pilot = models.ForeignKey("members.Member", on_delete=models.SET_NULL, null=True, blank=True, related_name="flights_as_tow_pilot")
    towplane = models.ForeignKey("Towplane", on_delete=models.SET_NULL, null=True, blank=True)
    duration = models.DurationField(blank=True, null=True)
    passenger = models.ForeignKey(Member, on_delete=models.SET_NULL, null=True, blank=True, related_name="flights_as_passenger")
    passenger_name = models.CharField(max_length=100, blank=True, help_text="Name of passenger if not a member")


    field = models.CharField(max_length=100)  # Copy from logsheet or input per-flight
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
    tow_cost_actual = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    rental_cost_actual = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)

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
                land_dt += timedelta(days=1)
    
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
    
from members.models import Member

class RevisionLog(models.Model):
    logsheet = models.ForeignKey("Logsheet", on_delete=models.CASCADE, related_name="revisions")
    revised_by = models.ForeignKey(Member, on_delete=models.SET_NULL, null=True)
    revised_at = models.DateTimeField(auto_now_add=True)
    note = models.TextField(blank=True)

    def __str__(self):
        return f"Revised by {self.revised_by} on {self.revised_at}"

class Towplane(models.Model):
    name = models.CharField(max_length=100)
    registration = models.CharField(max_length=50)  # e.g., N-number
    photo = models.ImageField(upload_to="towplane_photos/", blank=True, null=True)
    is_active = models.BooleanField(default=True)
    class Meta:
        ordering = ["name"]

    def __str__(self):
        status = " (Inactive)" if not self.is_active else ""
        return f"{self.name} ({self.registration})"

class Glider(models.Model):
    make = models.CharField(max_length=100)
    model = models.CharField(max_length=100)
    n_number = models.CharField(max_length=20, unique=True)  # Registration (e.g. N123AB)
    competition_number = models.CharField(max_length=10, blank=True)
    seats = models.PositiveIntegerField(default=2)
    picture = models.ImageField(upload_to="glider_photos/", blank=True, null=True)
    rental_rate = models.DecimalField(max_digits=6, decimal_places=2, blank=True, null=True)
    max_rental_rate = models.DecimalField(max_digits=6, decimal_places=2, blank=True, null=True)

    def __str__(self):
        parts = []
        if self.competition_number:
            parts.append(self.competition_number.upper())
        if self.n_number:
            parts.append(self.n_number.upper())
        if self.model:
            parts.append(self.model)
        return " / ".join(parts)
    
from django.db import models

class Airfield(models.Model):
    identifier = models.CharField(max_length=10, unique=True)  # e.g., KFRR
    name = models.CharField(max_length=100)  # e.g., Front Royal Warren County Airport
    photo = models.ImageField(upload_to='airfield_photos/', blank=True, null=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.identifier} – {self.name}"

from django.db import models
from members.models import Member
from .models import Towplane, Airfield  # Adjust import paths as needed

class Logsheet(models.Model):
    log_date = models.DateField()
    airfield = models.ForeignKey(Airfield, on_delete=models.PROTECT)
    created_by = models.ForeignKey(Member, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    finalized = models.BooleanField(default=False)

    # NEW: Duty crew assignments
    duty_officer = models.ForeignKey(Member, on_delete=models.SET_NULL, null=True, blank=True, related_name="log_duty_officer", limit_choices_to={"duty_officer": True})
    assistant_duty_officer = models.ForeignKey(Member, on_delete=models.SET_NULL, null=True, blank=True, related_name="log_assistant_duty_officer", limit_choices_to={"assistant_duty_officer": True})
    duty_instructor = models.ForeignKey(Member, on_delete=models.SET_NULL, null=True, blank=True, related_name="log_duty_instructor", limit_choices_to={"instructor": True})
    surge_instructor = models.ForeignKey(Member, on_delete=models.SET_NULL, null=True, blank=True, related_name="log_surge_instructor", limit_choices_to={"instructor": True})
    tow_pilot = models.ForeignKey(Member, on_delete=models.SET_NULL, null=True, blank=True, related_name="log_tow_pilot", limit_choices_to={"towpilot": True})
    surge_tow_pilot = models.ForeignKey(Member, on_delete=models.SET_NULL, null=True, blank=True, related_name="log_surge_tow_pilot", limit_choices_to={"towpilot": True})

    # NEW: Default towplane
    default_towplane = models.ForeignKey(Towplane, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        unique_together = ("log_date", "airfield")

    def __str__(self):
        return f"{self.log_date} @ {self.airfield}"

class TowRate(models.Model):
    altitude = models.PositiveIntegerField(help_text="Release altitude in feet (e.g. 2000)")
    price = models.DecimalField(max_digits=6, decimal_places=2, help_text="Price in USD")

    class Meta:
        ordering = ['altitude']

    def __str__(self):
        return f"{self.altitude} ft – ${self.price:.2f}"
    
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
            ("zelle", "Zelle")
            ],
        null=True,
        blank=True
    )
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        unique_together = ("logsheet", "member")

    def __str__(self):
        return f"{self.member.full_display_name} - {self.logsheet.log_date} ({self.payment_method or 'Unpaid'})"

    

