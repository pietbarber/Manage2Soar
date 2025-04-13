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

from django.db import models
from tinymce.models import HTMLField
from members.models import Member

class InstructionReport(models.Model):
    student = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="instruction_reports")
    instructor = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="given_instruction_reports")
    report_date = models.DateField()
    report_text = HTMLField(blank=True)  # Instructor's summary / essay
    simulator = models.BooleanField(default=False)  # 🖥️ Simulator session flag
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('student', 'instructor', 'report_date')
        ordering = ['-report_date']

    def __str__(self):
        return f"{self.student.full_display_name} – {self.report_date} by {self.instructor.full_display_name}"
    
    from django.db import models
from instructors.models import InstructionReport, TrainingLesson

SCORE_CHOICES = [
    ("1", "Introduced (Instructor flew)"),
    ("2", "Practiced (with instructor help)"),
    ("3", "Solo Standard"),
    ("4", "Checkride Standard"),
    ("!", "Needs Attention (!)")
]

class LessonScore(models.Model):
    report = models.ForeignKey(InstructionReport, on_delete=models.CASCADE, related_name="lesson_scores")
    lesson = models.ForeignKey(TrainingLesson, on_delete=models.CASCADE)
    score = models.CharField(max_length=2, choices=SCORE_CHOICES)

    class Meta:
        unique_together = ('report', 'lesson')
        ordering = ['lesson__code']

    def __str__(self):
        return f"{self.lesson.code} – {self.get_score_display()}"

class GroundInstruction(models.Model):
    student = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="ground_sessions")
    instructor = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="ground_given")
    date = models.DateField()
    location = models.CharField(max_length=100, blank=True, null=True)
    duration = models.DurationField(blank=True, null=True)
    lessons = models.ManyToManyField(TrainingLesson, blank=True)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date"]

    def __str__(self):
        return f"{self.date} – {self.student} w/ {self.instructor}"
