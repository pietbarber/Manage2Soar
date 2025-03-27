from datetime import timedelta
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.timezone import now
from tinymce.models import HTMLField
from .utils.avatar_generator import generate_identicon
import os

def biography_upload_path(instance, filename):
    return f'biography/{instance.member.username}/{filename}'

class Biography(models.Model):
    member = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    content = models.TextField(blank=True, null=True)
    uploaded_image = models.ImageField(upload_to=biography_upload_path, blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Biography of {self.member.get_full_name()}"

class Glider(models.Model):
    make = models.CharField(max_length=100)
    model = models.CharField(max_length=100)
    n_number = models.CharField(max_length=10, unique=True)
    competition_number = models.CharField(max_length=3, blank=True, null=True)
    number_of_seats = models.PositiveIntegerField(default=1)
    photo = models.ImageField(upload_to='glider_photos/', blank=True, null=True)
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
        return " ".join(parts)



class Member(AbstractUser):
   # Here are the legacy codes from the old database,
    # which you can use for reference when we do the migration
    # Legacy status codes:
    # M = Full Member
    # U = Student Member
    # Q = Family Member
    # F = Founding Member
    # H = Honorary Member
    # E = Introductory Member
    # C = SSEF Member (Scholarship)
    # I = Inactive
    # N = Non-Member
    # P = Probationary Member
    # T = Transient Member
    # A = FAST Member
    # S = Service Member

    MEMBERSHIP_STATUS_CHOICES = [
        ('Full Member', 'Full Member'),
        ('Student Member', 'Student Member'),
        ('Family Member', 'Family Member'),
        ('Founding Member', 'Founding Member'),
        ('Honorary Member', 'Honorary Member'),
        ('Introductory Member', 'Introductory Member'),
        ('SSEF Member', 'SSEF Member'),
        ('Inactive', 'Inactive'),
        ('Non-Member', 'Non-Member'),
        ('Pending', 'Pending'),
        ('Probationary Member', 'Probationary Member'),
        ('Transient Member', 'Transient Member'),
        ('FAST Member', 'FAST Member'),
        ('Service Member', 'Service Member'),
    ]
    US_STATE_CHOICES = [
        ('AL', 'Alabama'), ('AK', 'Alaska'), ('AZ', 'Arizona'), ('AR', 'Arkansas'),
        ('CA', 'California'), ('CO', 'Colorado'), ('CT', 'Connecticut'), ('DE', 'Delaware'),
        ('FL', 'Florida'), ('GA', 'Georgia'), ('HI', 'Hawaii'), ('ID', 'Idaho'),
        ('IL', 'Illinois'), ('IN', 'Indiana'), ('IA', 'Iowa'), ('KS', 'Kansas'),
        ('KY', 'Kentucky'), ('LA', 'Louisiana'), ('ME', 'Maine'), ('MD', 'Maryland'),
        ('MA', 'Massachusetts'), ('MI', 'Michigan'), ('MN', 'Minnesota'), ('MS', 'Mississippi'),
        ('MO', 'Missouri'), ('MT', 'Montana'), ('NE', 'Nebraska'), ('NV', 'Nevada'),
        ('NH', 'New Hampshire'), ('NJ', 'New Jersey'), ('NM', 'New Mexico'), ('NY', 'New York'),
        ('NC', 'North Carolina'), ('ND', 'North Dakota'), ('OH', 'Ohio'), ('OK', 'Oklahoma'),
        ('OR', 'Oregon'), ('PA', 'Pennsylvania'), ('RI', 'Rhode Island'), ('SC', 'South Carolina'),
        ('SD', 'South Dakota'), ('TN', 'Tennessee'), ('TX', 'Texas'), ('UT', 'Utah'),
        ('VT', 'Vermont'), ('VA', 'Virginia'), ('WA', 'Washington'), ('WV', 'West Virginia'),
        ('WI', 'Wisconsin'), ('WY', 'Wyoming')
    ]

    membership_status = models.CharField(
        max_length=20,
        choices=MEMBERSHIP_STATUS_CHOICES,
        default='Non-Member',
        blank=True,
        null=True,
    )

    NAME_SUFFIX_CHOICES = [
    ('', '—'),  # blank default
    ('Jr.', 'Jr.'),
    ('Sr.', 'Sr.'),
    ('II', 'II'),
    ('III', 'III'),
    ('IV', 'IV'),
    ('V', 'V'),
    ]

    # Additional name-related fields

    middle_initial = models.CharField(max_length=2, blank=True, null=True)
    nickname = models.CharField(max_length=50, blank=True, null=True)
    name_suffix = models.CharField(
        max_length=10,
        choices=NAME_SUFFIX_CHOICES,
        blank=True,
        null=True,
    )

    # Additional contact information fields
 
    SSA_member_number = models.CharField(max_length=20, unique=True, blank=True, null=True)
    legacy_username = models.CharField(max_length=50, unique=True, blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    mobile_phone = models.CharField(max_length=20, blank=True, null=True)
    country = models.CharField(max_length=2, blank=True, null=True, default='US')
    address = models.TextField(blank=True, null=True)
    city = models.CharField(max_length=50, blank=True, null=True)
    state_code = models.CharField(
        max_length=2,
        choices=US_STATE_CHOICES,
        blank=True,
        null=True
    )
    state_freeform = models.CharField(max_length=50, blank=True, null=True)
    zip_code = models.CharField(max_length=10, blank=True, null=True)
    profile_photo = models.ImageField(upload_to='profile_photos/', blank=True, null=True)
    GLIDER_RATING_CHOICES = [
        ('none', 'None'),
        ('student', 'Student'),
        ('transition', 'Transition'),
        ('private', 'Private'),
        ('commercial', 'Commercial'),
    ]
    glider_rating = models.CharField(
        max_length=10, choices=GLIDER_RATING_CHOICES, default='student'
    )

    instructor = models.BooleanField(default=False)
    towpilot = models.BooleanField(default=False)
    duty_officer = models.BooleanField(default=False)
    assistant_duty_officer = models.BooleanField(default=False)
    secretary = models.BooleanField(default=False)
    treasurer = models.BooleanField(default=False)
    webmaster = models.BooleanField(default=False)
    director = models.BooleanField(default=False)
    member_manager = models.BooleanField(default=False)

    glider_owned = models.ForeignKey(
        Glider,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='primary_owners'
    )

    second_glider_owned = models.ForeignKey(
        Glider,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='secondary_owners'
    )

    joined_club = models.DateField(blank=True, null=True)
    emergency_contact = models.TextField(blank=True, null=True)

    public_notes = HTMLField(blank=True, null=True)
    private_notes = HTMLField(blank=True, null=True)

    last_updated_by = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.profile_photo:
            # Only generate if no photo already exists
            filename = f"profile_{self.username}.png"
            file_path = os.path.join('generated_avatars', filename)

            # Prevent overwriting if avatar already exists
            if not os.path.exists(os.path.join('media', file_path)):
                generate_identicon(self.username, file_path)

            self.profile_photo = file_path

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

class Badge(models.Model):
    name = models.CharField(max_length=100, unique=True)
    image = models.ImageField(upload_to='badge_images/', blank=True, null=True)
    description = HTMLField(blank=True)
    order = models.PositiveIntegerField(default=0)  # 👈 Add this!

    class Meta:
        ordering = ['order']  # 👈 Ensure badges come out in the desired order

    def __str__(self):
        return self.name


class MemberBadge(models.Model):
    member = models.ForeignKey('Member', on_delete=models.CASCADE, related_name='badges')
    badge = models.ForeignKey(Badge, on_delete=models.CASCADE)
    date_awarded = models.DateField()
    notes = models.TextField(blank=True)

    class Meta:
        unique_together = ('member', 'badge')

    def __str__(self):
        return f"{self.member} - {self.badge.name}"
    

    #################################################################
    # Logsheet stuff follows 
    #################################################################

from django.db import models
from django.conf import settings

class Towplane(models.Model):
    name = models.CharField(max_length=100, unique=True)
    registration = models.CharField(max_length=20, blank=True)
    picture = models.ImageField(upload_to='towplane_photos/', blank=True, null=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Airfield(models.Model):
    identifier = models.CharField(max_length=10, unique=True)  # e.g., KFRR
    name = models.CharField(max_length=100)  # e.g., Front Royal Warren County Airport
    photo = models.ImageField(upload_to='airfield_photos/', blank=True, null=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.identifier} – {self.name}"


class FlightLog(models.Model):
    FLIGHT_TYPE_CHOICES = [
        ('Solo', 'Solo'),
        ('Dual', 'Dual'),
        ('Checkride', 'Checkride'),
        ('Demo', 'Demo'),
        ('Other', 'Other'),
    ]

    PAYS_CHOICES = [
        ('all', 'All'),
        ('half', 'Half'),
        ('rental', 'Rental'),
        ('tow', 'Tow'),
    ]

    flight_date = models.DateField()
    airfield = models.ForeignKey('Airfield', on_delete=models.PROTECT, null=True, blank=True)


    pilot = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='flights_flown')
    passenger = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='flights_passenger')
    instructor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='flights_instructed')
    towpilot = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='flights_towed')

    glider = models.ForeignKey("Glider", on_delete=models.SET_NULL, null=True)
    towplane = models.ForeignKey("Towplane", on_delete=models.SET_NULL, null=True, blank=True)

    takeoff_time = models.TimeField(null=True, blank=True)
    landing_time = models.TimeField(null=True, blank=True)
    flight_time = models.DurationField(null=True, blank=True, help_text="Total time of flight")

    release_altitude = models.PositiveIntegerField(help_text="In feet", null=True, blank=True)

    flight_type = models.CharField(max_length=20, choices=FLIGHT_TYPE_CHOICES, default='Solo', blank=True)

    exception = models.TextField(blank=True)

    alternate_payer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='flights_paid')
    pays = models.CharField(max_length=10, choices=PAYS_CHOICES, blank=True)

    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-flight_date', 'takeoff_time']

    def __str__(self):
        return f"{self.flight_date} - {self.pilot} in {self.glider} at {self.airfield}"
    
    def clean(self):
        # Prevent passenger/instructor if glider is single seat
        if self.glider.number_of_seats == 1:
            if self.passenger:
                raise ValidationError("Single-seat gliders cannot have a passenger.")
            if self.instructor:
                raise ValidationError("Single-seat gliders cannot have an instructor.")

    def clean(self):
        super().clean()
        errors = {}

        if self.glider:
            if self.glider.number_of_seats == 1:
                if self.passenger:
                    errors['passenger'] = "This glider only has one seat. It cannot have a passenger."
                if self.instructor:
                    errors['instructor'] = "This glider only has one seat. It cannot have an instructor."
        else:
            # Glider is optional or not yet selected
            pass
        
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.takeoff_time and self.landing_time:
            # Calculate flight duration
            takeoff_dt = now().replace(hour=self.takeoff_time.hour, minute=self.takeoff_time.minute)
            landing_dt = now().replace(hour=self.landing_time.hour, minute=self.landing_time.minute)
            if landing_dt < takeoff_dt:
                landing_dt += timedelta(days=1)  # Handle flights that land after midnight
            self.flight_time = landing_dt - takeoff_dt

        self.full_clean()  # Run clean() validations
        super().save(*args, **kwargs)

from django.utils import timezone
from .models import Member, Airfield

class FlightDay(models.Model):
    flight_date = models.DateField()
    airfield = models.ForeignKey(Airfield, on_delete=models.CASCADE)
    duty_officer = models.ForeignKey(Member, on_delete=models.SET_NULL, null=True, blank=True, related_name='flight_days_duty')
    instructor = models.ForeignKey(Member, on_delete=models.SET_NULL, null=True, blank=True, related_name='flight_days_instructing')
    towpilot = models.ForeignKey(Member, on_delete=models.SET_NULL, null=True, blank=True, related_name='flight_days_tow')
    assistant = models.ForeignKey(Member, on_delete=models.SET_NULL, null=True, blank=True, related_name='flight_days_assist')

    is_closed = models.BooleanField(default=False)
    notes = HTMLField(blank=True, null=True)

    def __str__(self):
        return f"{self.date} @ {self.airfield}"
