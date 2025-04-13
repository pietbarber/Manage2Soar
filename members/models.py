from datetime import timedelta
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.timezone import now
from tinymce.models import HTMLField
from .utils.avatar_generator import generate_identicon
import os
from django.contrib.auth.models import Group


def biography_upload_path(instance, filename):
    return f'biography/{instance.member.username}/{filename}'

class Biography(models.Model):
    member = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    content = HTMLField(blank=True, null=True)
    uploaded_image = models.ImageField(upload_to=biography_upload_path, blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Biographies"

    def __str__(self):
        return f"Biography of {self.member.get_full_name()}"


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

    from members.constants.membership import DEFAULT_ACTIVE_STATUSES, MEMBERSHIP_STATUS_CHOICES, US_STATE_CHOICES

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
        "logsheet.Glider",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="owners"
    )

    second_glider_owned = models.ForeignKey(
        "logsheet.Glider",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="secondary_owners"
    )

    joined_club = models.DateField(blank=True, null=True)
    emergency_contact = models.TextField(blank=True, null=True)

    public_notes = HTMLField(blank=True, null=True)
    private_notes = HTMLField(blank=True, null=True)

    last_updated_by = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True)


    @property
    def profile_image_url(self):
        from django.urls import reverse
        if self.profile_photo:
            return self.profile_photo.url
        return reverse('pydenticon', kwargs={'username': self.username})


    @property
    def full_display_name(self):
        if self.nickname:
            first = f'{self.first_name} "{self.nickname}"'
        else:
            first = self.first_name

        name = f"{first} {self.middle_initial or ''} {self.last_name}".strip()

        if self.name_suffix:
            name = f"{name}, {self.name_suffix}"
        if self.membership_status == "Deceased":
            name += "†"
        return " ".join(name.split())  # Normalize spaces


    def is_active_member(self):
        return self.membership_status in ['active', 'student', 'ssef', 'fast', 'service']

    def save(self, *args, **kwargs):
        self.is_staff = self.instructor or self.member_manager

        if not self.profile_photo:
            # Only generate if no photo already exists
            filename = f"profile_{self.username}.png"
            file_path = os.path.join('generated_avatars', filename)

            # Prevent overwriting if avatar already exists
            if not os.path.exists(os.path.join('media', file_path)):
                generate_identicon(self.username, file_path)

            self.profile_photo = file_path

        super().save(*args, **kwargs)

        if self.instructor:
            try:
                group = Group.objects.get(name="Instructor Admins")
                if not self.groups.filter(id=group.id).exists():
                    self.groups.add(group)
            except Group.DoesNotExist:
                pass  # optionally log this

            # ✅ Assign member manager to Member Managers group
        if self.member_manager:
            try:
                group = Group.objects.get(name="Member Managers")
                if not self.groups.filter(id=group.id).exists():
                    self.groups.add(group)
            except Group.DoesNotExist:
                pass



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
    