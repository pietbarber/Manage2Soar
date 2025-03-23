from django.contrib.auth.models import AbstractUser
from django.contrib.auth.models import User
from django.db import models
from ckeditor.fields import RichTextField

class Member(AbstractUser):
    is_instructor = models.BooleanField(default=False)
    bio = models.TextField(blank=True, null=True)

class Member(models.Model):
    SSA_member_number = models.CharField(max_length=20, unique=True)
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    city = models.CharField(max_length=50, blank=True, null=True)
    state = models.CharField(max_length=20, blank=True, null=True)
    zip_code = models.CharField(max_length=10, blank=True, null=True)
        # Define choices for Glider Rating
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

    # Glider Ownership
    glider_owned = models.CharField(max_length=255, blank=True, null=True)
    second_glider_owned = models.CharField(max_length=255, blank=True, null=True)

    # Membership Info
    joined_club = models.DateField(blank=True, null=True)

    # Multi-line Text Fields
    emergency_contact = models.TextField(blank=True, null=True)
    
    # Rich Text Fields (Using Django CKEditor for HTML Support)
    public_notes = RichTextField(blank=True, null=True)
    private_notes = RichTextField(blank=True, null=True)

    last_updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.glider_rating})"

class Member(AbstractUser):
    glider_rating = models.CharField(
        max_length=10,
        choices=[
            ("student", "Student"),
            ("transition", "Transition"),
            ("private", "Private"),
            ("commercial", "Commercial"),
        ],
        default="student",
    )