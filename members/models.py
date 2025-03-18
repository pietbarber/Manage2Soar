from django.contrib.auth.models import AbstractUser
from django.db import models

class Member(AbstractUser):
    is_instructor = models.BooleanField(default=False)
    bio = models.TextField(blank=True, null=True)

