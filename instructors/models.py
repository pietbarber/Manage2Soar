from django.db import models
from tinymce.models import HTMLField
class TrainingPhase(models.Model):
    number = models.PositiveSmallIntegerField()
    name = models.CharField(max_length=100)

    class Meta:
        ordering = ["number"]

    def __str__(self):
        return f"{self.number} – {self.name}"

class TrainingLesson(models.Model):
    code = models.CharField(max_length=5, unique=True)  # e.g., "2l"
    title = models.CharField(max_length=100)  # e.g., "Normal Landing"
    description = HTMLField(blank=True)  # full lesson content from .shtml

    # FAA compliance tracking (from legacy fields)
    far_requirement = models.CharField(max_length=20, blank=True)       # e.g., "61.87(i)(16)"
    pts_reference = models.CharField(max_length=30, blank=True)         # e.g., "61.107(b)(6)(iv)"
    phase = models.ForeignKey(TrainingPhase, on_delete=models.SET_NULL, null=True, blank=True, related_name="lessons")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["code"]

    def is_required_for_solo(self):
        return bool(self.far_requirement)

    def is_required_for_private(self):
        return bool(self.pts_reference)

    def __str__(self):
        return f"{self.code} – {self.title}"

class SyllabusDocument(models.Model):
    slug = models.SlugField(unique=True)  # e.g. 'header', 'materials'
    title = models.CharField(max_length=200)
    content = HTMLField()

    def __str__(self):
        return self.title
