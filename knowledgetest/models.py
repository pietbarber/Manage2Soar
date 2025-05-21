from django.db import models
from django.conf import settings
from tinymce.models import HTMLField
from members.models import Member

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
        QuestionCategory,
        db_column='code',
        to_field='code',
        on_delete=models.CASCADE
    )
    question_text = HTMLField()
    option_a = HTMLField()
    option_b = HTMLField()
    option_c = HTMLField()
    option_d = HTMLField()

    CORRECT_CHOICES = [
        ('A', 'A'),
        ('B', 'B'),
        ('C', 'C'),
        ('D', 'D'),
    ]
    correct_answer = models.CharField(max_length=1, choices=CORRECT_CHOICES)
    explanation = HTMLField(blank=True)
    last_updated = models.DateField(null=True, blank=True)
    updated_by = models.ForeignKey(
        Member,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='updated_questions',
        help_text='Member who last updated this question'
    )
    media = models.FileField(
        upload_to='written_test_media/',
        null=True,
        blank=True,
        help_text='Optional image or file attachment for the question'
    )

    def __str__(self):
        text = self.question_text
        return f"Q{self.qnum}: {text[:50]}..."

# Templates or ad-hoc tests
class WrittenTestTemplate(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    questions = models.ManyToManyField(
        Question,
        through='WrittenTestTemplateQuestion',
        related_name='templates'
    )
    pass_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=100,
        help_text='Minimum score (in %) required to pass'
    )
    time_limit = models.DurationField(
        null=True,
        blank=True,
        help_text='Optional time limit for the test'
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name='created_written_tests'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class WrittenTestTemplateQuestion(models.Model):
    template = models.ForeignKey(
        WrittenTestTemplate,
        on_delete=models.CASCADE
    )
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE
    )
    order = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ('template', 'question')
        ordering = ['order']

# Student test attempts and results
class WrittenTestAttempt(models.Model):
    template = models.ForeignKey(
        WrittenTestTemplate,
        on_delete=models.PROTECT,
        related_name='attempts'
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='written_test_attempts',
        on_delete=models.PROTECT
    )
    instructor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name='graded_written_tests',
        on_delete=models.SET_NULL
    )
    date_taken = models.DateTimeField(auto_now_add=True)
    score_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True
    )
    passed = models.BooleanField(default=False)
    time_taken = models.DurationField(
        null=True,
        blank=True,
        help_text='Duration student took to complete the test'
    )

    def __str__(self):
        status = 'Passed' if self.passed else 'Failed'
        return f"{self.student} - {self.template.name} on {self.date_taken.date()} ({status})"

class WrittenTestAnswer(models.Model):
    attempt = models.ForeignKey(
        WrittenTestAttempt,
        related_name='answers',
        on_delete=models.CASCADE
    )
    question = models.ForeignKey(
        Question,
        on_delete=models.PROTECT
    )
    selected_answer = models.CharField(max_length=1, choices=Question.CORRECT_CHOICES)
    is_correct = models.BooleanField()

    class Meta:
        unique_together = ('attempt', 'question')

    def __str__(self):
        return f"{self.attempt.student} - Q{self.question.qnum}: {self.selected_answer}"