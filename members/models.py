from django.contrib.auth.models import AbstractUser
from django.db import models

class Member(AbstractUser):
    MEMBERSHIP_STATUS_CHOICES = [
        ('Full Member', 'Full Member'),
        ('Student Member', 'Student Member'),
        ('Family Member', 'Family Member'),
        ('Honorary Member', 'Honorary Member'),
        ('Life Member', 'Life Member'),
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

    is_instructor = models.BooleanField(default=False)
    is_duty_officer = models.BooleanField(default=False)
    is_assistant_duty_officer = models.BooleanField(default=False)
    secretary = models.BooleanField(default=False)
    treasurer = models.BooleanField(default=False)
    webmaster = models.BooleanField(default=False)

    glider_owned = models.CharField(max_length=255, blank=True, null=True)
    second_glider_owned = models.CharField(max_length=255, blank=True, null=True)

    joined_club = models.DateField(blank=True, null=True)
    emergency_contact = models.TextField(blank=True, null=True)

    from tinymce.models import HTMLField
    public_notes = HTMLField(blank=True, null=True)
    private_notes = HTMLField(blank=True, null=True)

    last_updated_by = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name}"
