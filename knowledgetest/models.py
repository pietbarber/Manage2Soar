from decimal import Decimal

from django.conf import settings
from django.db import models
from tinymce.models import HTMLField

from members.models import Member
from utils.upload_entropy import upload_written_test_media

# Categories (legacy qcodes)


class QuestionCategory(models.Model):
    code = models.CharField(max_length=10, primary_key=True)
    description = models.CharField(max_length=255)

    def __str__(self):
        return self.code


# Test bank questions (legacy test_contents)


class Question(models.Model):
    qnum = models.IntegerField(primary_key=True)
    category = models.ForeignKey(
        QuestionCategory, db_column="code", to_field="code", on_delete=models.CASCADE
    )
    question_text = HTMLField()
    option_a = HTMLField()
    option_b = HTMLField()
    option_c = HTMLField()
    option_d = HTMLField()

    CORRECT_CHOICES = [
        ("A", "A"),
        ("B", "B"),
        ("C", "C"),
        ("D", "D"),
    ]
    correct_answer = models.CharField(max_length=1, choices=CORRECT_CHOICES)
    explanation = HTMLField(blank=True)
    last_updated = models.DateField(null=True, blank=True)
    updated_by = models.ForeignKey(
        Member,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="updated_questions",
        help_text="Member who last updated this question",
    )
    media = models.FileField(
        upload_to=upload_written_test_media,
        null=True,
        blank=True,
        help_text="Optional image or file attachment for the question",
    )

    def __str__(self):
        text = self.question_text
        return f"Q{self.qnum}: {text[:50]}..."


# Templates or ad-hoc tests


class WrittenTestTemplate(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    questions = models.ManyToManyField(
        Question, through="WrittenTestTemplateQuestion", related_name="templates"
    )
    pass_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("100.00"),
        help_text="Minimum score (in %) required to pass",
    )
    time_limit = models.DurationField(
        null=True, blank=True, help_text="Optional time limit for the test"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="created_written_tests",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class WrittenTestTemplateQuestion(models.Model):
    template = models.ForeignKey(WrittenTestTemplate, on_delete=models.CASCADE)
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ("template", "question")
        ordering = ["order"]


# Student test attempts and results


class WrittenTestAttempt(models.Model):
    template = models.ForeignKey(
        WrittenTestTemplate, on_delete=models.PROTECT, related_name="attempts"
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="written_test_attempts",
        on_delete=models.PROTECT,
    )
    instructor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="graded_written_tests",
        on_delete=models.SET_NULL,
    )
    date_taken = models.DateTimeField(auto_now_add=True)
    score_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    passed = models.BooleanField(default=False)
    time_taken = models.DurationField(
        null=True, blank=True, help_text="Duration student took to complete the test"
    )

    def __str__(self):
        status = "Passed" if self.passed else "Failed"
        return f"{self.student} - {self.template.name} on {self.date_taken.date()} ({status})"


class WrittenTestAnswer(models.Model):
    attempt = models.ForeignKey(
        WrittenTestAttempt, related_name="answers", on_delete=models.CASCADE
    )
    question = models.ForeignKey(Question, on_delete=models.PROTECT)
    selected_answer = models.CharField(max_length=1, choices=Question.CORRECT_CHOICES)
    is_correct = models.BooleanField()

    class Meta:
        unique_together = ("attempt", "question")

    def __str__(self):
        return f"{self.attempt.student} - Q{self.question.qnum}: {self.selected_answer}"


class WrittenTestAssignment(models.Model):
    template = models.ForeignKey(
        WrittenTestTemplate, on_delete=models.CASCADE, related_name="assignments"
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="assigned_written_tests",
    )
    instructor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="issued_written_tests",
    )
    assigned_at = models.DateTimeField(auto_now_add=True)
    completed = models.BooleanField(default=False)
    attempt = models.OneToOneField(
        WrittenTestAttempt,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        unique_together = ("template", "student")

    def __str__(self):
        return f"{self.template.name} → {self.student}"


# Test Presets - configurable test templates


class TestPreset(models.Model):
    """
    Django model for managing quiz test presets and configurations.
    Not a pytest test class - this is a database model.
    """

    __test__ = False  # Explicitly tell pytest this is not a test class

    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Name of the test preset (e.g., 'ASK21', 'PW5', 'Duty Officer')",
    )
    description = models.TextField(
        blank=True, help_text="Optional description of what this preset is for"
    )
    category_weights = models.JSONField(
        default=dict,
        help_text="Dictionary mapping question category codes to the number of questions to include",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this preset is available for creating new tests",
    )
    sort_order = models.PositiveIntegerField(
        default=100, help_text="Display order (lower numbers appear first)"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = "Test Preset"
        verbose_name_plural = "Test Presets"

    def __str__(self):
        return self.name

    def delete(self, *args, **kwargs):
        """
        Override delete. No automatic protection; admins must manually verify
        that no templates reference this preset before deletion.
        See docs/admin/test-presets.md for manual review steps.
        """
        super().delete(*args, **kwargs)

    @classmethod
    def get_active_presets(cls):
        """Get all test presets that are marked as active."""
        return cls.objects.filter(is_active=True).order_by("sort_order", "name")

    @classmethod
    def get_presets_as_dict(cls):
        """Get active presets as a dictionary matching the old format."""
        presets = {}
        for preset in cls.get_active_presets():
            presets[preset.name] = preset.category_weights
        return presets

    def get_total_questions(self):
        """Calculate the total number of questions in this preset."""
        return sum(self.category_weights.values()) if self.category_weights else 0
