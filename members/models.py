from django.contrib.auth.models import AbstractUser
from django.db import models

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
    MEMBERSHIP_STATUS_CHOICES = [
        ('Full Member', 'Full Member'),
        ('Student Member', 'Student Member'),
        ('Family Member', 'Family Member'),
        ('Founding Member', 'Founding Member'),
        ('Honorary Member', 'Honorary Member'),
        ('Emeritus Member', 'Emeritus Member'),
        ('SSEF Member', 'SSEF Member'),
        ('Temporary Member', 'Temporary Member'),
        ('Introductory Member', 'Introductory Member'),
        ('Inactive', 'Inactive'),
        ('Non-Member', 'Non-Member'),
    ]

    membership_status = models.CharField(
        max_length=20,
        choices=MEMBERSHIP_STATUS_CHOICES,
        default='Non-Member',
        blank=True,
        null=True,
    )

 
    SSA_member_number = models.CharField(max_length=20, unique=True, blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    mobile_phone = models.CharField(max_length=20, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    city = models.CharField(max_length=50, blank=True, null=True)
    state = models.CharField(max_length=20, blank=True, null=True)
    zip_code = models.CharField(max_length=10, blank=True, null=True)
    profile_photo = models.ImageField(upload_to='profile_photos/', blank=True, null=True)
    GLIDER_RATING_CHOICES = [
        ('student', 'Student'),
        ('transition', 'Transition'),
        ('private', 'Private'),
        ('commercial', 'Commercial'),
    ]
    glider_rating = models.CharField(
        max_length=10, choices=GLIDER_RATING_CHOICES, default='student'
    )

    instructor = models.BooleanField(default=False)
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

    from tinymce.models import HTMLField
    public_notes = HTMLField(blank=True, null=True)
    private_notes = HTMLField(blank=True, null=True)

    last_updated_by = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

