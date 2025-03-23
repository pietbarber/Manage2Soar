from django.contrib.auth.models import AbstractUser
from django.contrib.auth.models import User
from django.db import models
from tinymce.models import HTMLField

class Member(AbstractUser):
    SSA_member_number = models.CharField(max_length=20, unique=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    city = models.CharField(max_length=50, blank=True, null=True)
    state = models.CharField(max_length=20, blank=True, null=True)
    zip_code = models.CharField(max_length=10, blank=True, null=True)

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
    membership_status = models.CharField(
        max_length=20,
        choices=[
            ('Full Member', 'Full Member'),
            ('Student Member', 'Student Member'),
            ('Inactive', 'Inactive'),
        ]
    )

    glider_owned = models.CharField(max_length=255, blank=True, null=True)
    second_glider_owned = models.CharField(max_length=255, blank=True, null=True)

    joined_club = models.DateField(blank=True, null=True)
    emergency_contact = models.TextField(blank=True, null=True)

    public_notes = HTMLField(blank=True, null=True)
    private_notes = HTMLField(blank=True, null=True)

    last_updated_by = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True)

    # Required for Django's custom user model
    username = models.CharField(max_length=150, unique=True)
    email = models.EmailField(unique=True)
    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ["email", "first_name", "last_name"]

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.glider_rating})"
