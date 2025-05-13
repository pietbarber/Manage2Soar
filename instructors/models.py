from django.db import models
from tinymce.models import HTMLField
from members.models import Member

SCORE_CHOICES = [
    ("1", "Introduced (Instructor flew)"),
    ("2", "Practiced (with instructor help)"),
    ("3", "Solo Standard"),
    ("4", "Checkride Standard"),
    ("!", "Needs Attention (!)")
]


####################################################
# TrainingPhase model
#
# Represents a grouping phase in the training syllabus, such as "Before We Fly".
# Each phase has a numeric order and a human-readable name.
#
# Fields:
# - number: Ordering index for the phase.
# - name: Title of the phase.
#
# Methods:
# - __str__: Returns a string combining number and name.
####################################################
class TrainingPhase(models.Model):
    number = models.PositiveSmallIntegerField()
    name = models.CharField(max_length=100)

    class Meta:
        ordering = ["number"]

    def __str__(self):
        return f"{self.number} – {self.name}"

####################################################
# TrainingLesson model
#
# Defines an individual lesson in the syllabus.
# Lessons include codes, titles, detailed HTML content, and references
# to FAA requirements for solo or private certification.
#
# Fields:
# - code: Unique short identifier (e.g., "2l").
# - title: Lesson title (e.g., "Normal Landing").
# - description: Full HTML content of the lesson.
# - far_requirement: Text of the FAR citation for solo requirements.
# - pts_reference: Text of the PTS citation for private rating requirements.
# - phase: Link to TrainingPhase; may be null for unphased lessons.
# - created_at, updated_at: Timestamps for audit.
#
# Methods:
# - is_required_for_solo: True if far_requirement is non-empty.
# - is_required_for_private: True if pts_reference is non-empty.
# - __str__: Returns code and title.
####################################################
class TrainingLesson(models.Model):
    code = models.CharField(max_length=5, unique=True)  # e.g., "2l"
    title = models.CharField(max_length=100)  # e.g., "Normal Landing"
    description = HTMLField(blank=True)  # full lesson content from .shtml

    # FAA compliance tracking (from legacy fields)
    far_requirement = models.CharField(max_length=20, blank=True)       # e.g., "61.87(i)(16)"
    pts_reference = models.CharField(max_length=30, blank=True)         # e.g., "61.107(b)(6)(iv)"
    phase = models.ForeignKey(
        TrainingPhase,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lessons"
    )

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

####################################################
# SyllabusDocument model
#
# Stores HTML documents associated with the syllabus, such as a header
# or supplemental materials. Documents are identified by a slug.
#
# Fields:
# - slug: Unique key for retrieval (e.g., 'header').
# - title: Human-friendly document title.
# - content: Full HTML content.
#
# Methods:
# - __str__: Returns the document title.
####################################################
class SyllabusDocument(models.Model):
    slug = models.SlugField(unique=True)  # e.g. 'header', 'materials'
    title = models.CharField(max_length=200)
    content = HTMLField()

    def __str__(self):
        return self.title

####################################################
# InstructionReport model
#
# Records instructor evaluations after a flight session or simulator.
# Each report is unique per student, instructor, and flight date.
#
# Fields:
# - student: Student member.
# - instructor: Instructor member.
# - report_date: Date of the session.
# - report_text: HTML summary or essay.
# - simulator: Flag indicating a simulator session.
# - created_at, updated_at: Audit timestamps.
#
# Methods:
# - __str__: Returns a summary string of student, date, and instructor.
####################################################
class InstructionReport(models.Model):
    student = models.ForeignKey(
        Member,
        on_delete=models.CASCADE,
        related_name="instruction_reports"
    )
    instructor = models.ForeignKey(
        Member,
        on_delete=models.CASCADE,
        related_name="given_instruction_reports"
    )
    report_date = models.DateField()
    report_text = HTMLField(blank=True)  # Instructor's summary / essay
    simulator = models.BooleanField(default=False)  # 🖥️ Simulator session flag
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('student', 'instructor', 'report_date')
        ordering = ['-report_date']

    def __str__(self):
        return (
            f"{self.student.full_display_name} – {self.report_date}"  
            f" by {self.instructor.full_display_name}"
        )

####################################################
# LessonScore model
#
# Links an InstructionReport to individual TrainingLessons with a score.
# Scores reflect proficiency levels from introduction to checkride standard.
#
# Fields:
# - report: Reference to the InstructionReport.
# - lesson: Reference to the TrainingLesson.
# - score: Choice field from SCORE_CHOICES.
####################################################
class LessonScore(models.Model):
    report = models.ForeignKey(
        InstructionReport,
        on_delete=models.CASCADE,
        related_name="lesson_scores"
    )
    lesson = models.ForeignKey(TrainingLesson, on_delete=models.CASCADE)
    score = models.CharField(max_length=2, choices=SCORE_CHOICES)

    class Meta:
        unique_together = ('report', 'lesson')
        ordering = ['lesson__code']

####################################################
# GroundInstruction model
#
# Logs non-flight instruction sessions, including ground briefs and simulator.
# Sessions can include optional duration and location metadata.
#
# Fields:
# - student: Student member.
# - instructor: Instructor member.
# - date: Date of the session.
# - location: Optional location description.
# - duration: Optional duration of session.
# - notes: HTML notes from instructor.
# - created_at, updated_at: Audit timestamps.
#
# Methods:
# - __str__: Summary with date, student, and instructor.
####################################################
class GroundInstruction(models.Model):
    student = models.ForeignKey(
        Member,
        on_delete=models.CASCADE,
        related_name="ground_sessions"
    )
    instructor = models.ForeignKey(
        Member,
        on_delete=models.CASCADE,
        related_name="ground_given"
    )
    date = models.DateField()
    location = models.CharField(max_length=100, blank=True, null=True)
    duration = models.DurationField(blank=True, null=True)
    notes = HTMLField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date"]

    def __str__(self):
        return f"{self.date} – {self.student} w/ {self.instructor}"

####################################################
# GroundLessonScore model
#
# Records lesson-level scores for GroundInstruction sessions.
# Similar to LessonScore but for non-flight instruction.
#
# Fields:
# - session: Reference to GroundInstruction.
# - lesson: Reference to TrainingLesson.
# - score: Choice field from SCORE_CHOICES.
#
# Methods:
# - __str__: Returns lesson code and score display.
####################################################
class GroundLessonScore(models.Model):
    session = models.ForeignKey(
        "GroundInstruction",
        on_delete=models.CASCADE,
        related_name="lesson_scores"
    )
    lesson = models.ForeignKey("TrainingLesson", on_delete=models.CASCADE)
    score = models.CharField(max_length=2, choices=SCORE_CHOICES)

    class Meta:
        unique_together = ("session", "lesson")
        ordering = ["lesson__code"]

    def __str__(self):
        return f"{self.lesson.code} – {self.get_score_display()}"

####################################################
# ClubQualificationType model
#
# Defines types of club qualifications (e.g., CFI, ASK-Back). Each type may
# include an icon and tooltip, and apply to students, rated pilots, or both.
#
# Fields:
# - code: Unique identifier.
# - name: Human-friendly name.
# - icon: Optional image for UI.
# - applies_to: Scope of qualification.
# - is_obsolete: Soft-delete flag.
# - tooltip: Text description for UI hints.

####################################################
class ClubQualificationType(models.Model):
    code = models.CharField(max_length=30, unique=True)  # e.g. 'CFI', 'ASK-Back'
    name = models.CharField(max_length=100)              # Human-friendly name
    icon = models.ImageField(upload_to='quals/icons/', null=True, blank=True)
    applies_to = models.CharField(
        max_length=10,
        choices=[('student', 'Student'), ('rated', 'Rated'), ('both', 'Both')],
        default='both'
    )
    is_obsolete = models.BooleanField(default=False)
    tooltip = models.TextField(blank=True)

    def __str__(self):
        return self.name

####################################################
# MemberQualification model
#
# Links a Member to a ClubQualificationType with a status and metadata.
# Tracks award date, expiration, and whether it was imported from legacy data.
#
# Fields:
# - member: Reference to Member.
# - qualification: Reference to ClubQualificationType.
# - is_qualified: Current qualification status.
# - instructor: Issuing instructor (optional).
# - date_awarded, expiration_date: Temporal fields.
# - notes: Optional text.
# - imported: Flag for legacy import.
####################################################
class MemberQualification(models.Model):
    member = models.ForeignKey(Member, on_delete=models.CASCADE)
    qualification = models.ForeignKey(ClubQualificationType, on_delete=models.CASCADE)
    is_qualified = models.BooleanField(default=True)
    instructor = models.ForeignKey(
        Member,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='issued_quals'
    )
    date_awarded = models.DateField(null=True, blank=True)
    expiration_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    imported = models.BooleanField(default=False)  # track legacy-imported quals

    class Meta:
        unique_together = ('member', 'qualification')

    def __str__(self):
        return f"{self.member} – {self.qualification.code}"

####################################################
# StudentProgressSnapshot model
#
# Precomputed summary of a student’s progress for fast dashboard rendering.
# Stores percentages of completed solo and checkride lessons, total sessions,
# and timestamp of last update.
#
# Fields:
# - student: OneToOne reference to Member.
# - solo_progress: Float [0.0–1.0] percent complete for solo.
# - checkride_progress: Float [0.0–1.0] percent complete for rating.
# - sessions: Integer total of ground + flight instruction sessions.
# - last_updated: Timestamp auto-updated on save.
####################################################
class StudentProgressSnapshot(models.Model):
    student = models.OneToOneField(Member, on_delete=models.CASCADE)
    solo_progress = models.FloatField(default=0.0)       # 0.0 to 1.0
    checkride_progress = models.FloatField(default=0.0)  # 0.0 to 1.0
    sessions = models.IntegerField(default=0)            # total instructor sessions
    last_updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Progress for {self.student.full_display_name}"
