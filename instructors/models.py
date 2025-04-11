from django.db import models
from tinymce.models import HTMLField

class TrainingLesson(models.Model):
    code = models.CharField(max_length=5, unique=True)  # e.g., "2l"
    title = models.CharField(max_length=100)  # e.g., "Normal Landing"
    description = HTMLField(blank=True)  # full lesson content from .shtml

    # FAA compliance tracking (from legacy fields)
    far_requirement = models.CharField(max_length=20, blank=True)       # e.g., "61.87(i)(16)"
    pts_reference = models.CharField(max_length=30, blank=True)         # e.g., "61.107(b)(6)(iv)"

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def is_required_for_solo(self):
        return self.far_requirement.startswith("61.87")

    def is_required_for_private(self):
        return self.pts_reference.startswith("61.107")

    def __str__(self):
        return f"{self.code} – {self.title}"
