## See Also
- [README (App Overview)](README.md)
- [Management Commands](management.md)
- [Signals](signals.md)
- [Utilities](utils.md)
- [Views](views.md)
- [Decorators](decorators.md)
# Models Reference

Detailed descriptions of all Django models in the **instructors** app.

---

## Database Schema

```mermaid
erDiagram
    Member ||--o{ TrainingLesson : student
    Member ||--o{ TrainingLesson : instructor
    Member ||--o{ InstructionReport : student
    Member ||--o{ InstructionReport : instructor
    Member ||--o{ GroundInstruction : student
    Member ||--o{ GroundInstruction : instructor
    Member ||--o{ MemberQualification : member
    Member ||--o{ StudentProgressSnapshot : student
    
    TrainingPhase {
        int id PK
        string name
        text description
        int sequence_order
        boolean is_solo_phase
        boolean active
    }
    
    TrainingLesson {
        int id PK
        int student_id FK
        int instructor_id FK
        int phase_id FK
        int syllabus_document_id FK
        date lesson_date
        time duration
        text pre_flight_notes
        text post_flight_notes
        string lesson_status
        decimal grade_score
        boolean phase_complete
        datetime created_at
        datetime updated_at
    }
    
    SyllabusDocument {
        int id PK
        string title
        text content
        int phase_id FK
        int lesson_number
        boolean required
        int order
        boolean active
    }
    
    InstructionReport {
        int id PK
        int student_id FK
        int instructor_id FK
        date report_date
        text essay
        text student_performance
        text areas_for_improvement
        text next_lesson_focus
        boolean student_ready_for_solo
        boolean student_ready_for_checkride
        datetime created_at
        datetime updated_at
    }
    
    LessonScore {
        int id PK
        int instruction_report_id FK
        int syllabus_document_id FK
        int score
        text notes
    }
    
    GroundInstruction {
        int id PK
        int student_id FK
        int instructor_id FK
        date session_date
        time duration
        string topic
        text content_covered
        text student_questions
        text homework_assigned
        decimal grade_score
        datetime created_at
        datetime updated_at
    }
    
    GroundLessonScore {
        int id PK
        int ground_instruction_id FK
        int syllabus_document_id FK
        int score
        text notes
    }
    
    ClubQualificationType {
        int id PK
        string name
        text description
        boolean requires_instructor_signoff
        boolean requires_checkride
        int prerequisite_hours
        boolean active
    }
    
    MemberQualification {
        int id PK
        int member_id FK
        int qualification_type_id FK
        date date_earned
        int instructor_id FK
        text notes
        boolean active
        datetime created_at
        datetime updated_at
    }
    
    StudentProgressSnapshot {
        int id PK
        int student_id FK
        date snapshot_date
        json progress_data
        int total_lessons
        decimal avg_score
        boolean solo_ready
        boolean checkride_ready
        datetime created_at
    }
    
    TrainingPhase ||--o{ SyllabusDocument : contains
    TrainingPhase ||--o{ TrainingLesson : organized_by
    SyllabusDocument ||--o{ TrainingLesson : lesson_plan
    SyllabusDocument ||--o{ LessonScore : scored_on
    SyllabusDocument ||--o{ GroundLessonScore : ground_score
    InstructionReport ||--o{ LessonScore : contains_scores
    GroundInstruction ||--o{ GroundLessonScore : scored_lesson
    ClubQualificationType ||--o{ MemberQualification : qualification_type
    Member ||--o{ MemberQualification : instructor_signoff
```
---

## TrainingPhase

High-level grouping for lessons in the syllabus (e.g., "Before We Fly").

**Fields**

* `number` (PositiveSmallIntegerField): Ordering index for the phase.
* `name` (CharField): Human-readable title of the phase.

**Meta**

* `ordering = ["number"]`

**Methods**

* `__str__()`: Returns `"{number} – {name}"`.

---

## TrainingLesson

Defines a single lesson, with FAA references and rich HTML content.

**Fields**

* `code` (CharField): Unique short identifier (e.g., "2l").
* `title` (CharField): Lesson title (e.g., "Normal Landing").
* `description` (HTMLField): Full HTML content of the lesson.
* `far_requirement` (CharField): FAR citation text for solo endorsement.
* `pts_reference` (CharField): PTS citation text for private rating.
* `phase` (ForeignKey → TrainingPhase): Optional grouping phase.
* `created_at` (DateTimeField): Timestamp of creation.
* `updated_at` (DateTimeField): Timestamp of last update.

**Meta**

* `ordering = ["code"]`

**Methods**

* `is_required_for_solo()`: `True` if `far_requirement` is non-empty.
* `is_required_for_private()`: `True` if `pts_reference` is non-empty.
* `__str__()`: Returns `"{code} – {title}"`.

---

## SyllabusDocument

HTML documents tied to the syllabus (header, supplemental materials).

**Fields**

* `slug` (SlugField): Unique key (e.g., 'header').
* `title` (CharField): Document title.
* `content` (HTMLField): Full HTML content.

**Methods**

* `__str__()`: Returns `title`.

---

## InstructionReport

Flight‐based instructor evaluations submitted per student/date.

**Fields**

* `student` (ForeignKey → Member): Student receiving instruction.
* `instructor` (ForeignKey → Member): Instructor giving instruction.
* `report_date` (DateField): Date of the session.
* `report_text` (HTMLField): Narrative summary.
* `simulator` (BooleanField): Flag for simulator vs flight.
* `created_at`, `updated_at` (DateTimeField): Audit timestamps.

**Meta**

* `unique_together = ('student', 'instructor', 'report_date')`
* `ordering = ['-report_date']`

**Methods**

* `__str__()`: Returns `"{student.full_display_name} – {report_date} by {instructor.full_display_name}"`.

---

## LessonScore

Associates a `TrainingLesson` with a numeric proficiency score under an `InstructionReport`.

**Fields**

* `report` (ForeignKey → InstructionReport)
* `lesson` (ForeignKey → TrainingLesson)
* `score` (CharField): Choice from `SCORE_CHOICES`.

**Meta**

* `unique_together = ('report', 'lesson')`
* `ordering = ['lesson__code']`

---

## GroundInstruction

Logs non-flight instructional sessions in a ground or simulator context.

**Fields**

* `student` (ForeignKey → Member)
* `instructor` (ForeignKey → Member)
* `date` (DateField)
* `location` (CharField, optional)
* `duration` (DurationField, optional)
* `notes` (HTMLField, optional)
* `created_at`, `updated_at` (DateTimeField)

**Meta**

* `ordering = ['-date']`

**Methods**

* `__str__()`: Returns `"{date} – {student} w/ {instructor}"`.

---

## GroundLessonScore

Stores lesson‐level scores tied to a `GroundInstruction` session.

**Fields**

* `session` (ForeignKey → GroundInstruction)
* `lesson` (ForeignKey → TrainingLesson)
* `score` (CharField): Choice from `SCORE_CHOICES`.

**Meta**

* `unique_together = ('session', 'lesson')`
* `ordering = ['lesson__code']`

**Methods**

* `__str__()`: Returns `"{lesson.code} – {get_score_display()}"`.

---

## ClubQualificationType

Defines various club qualifications (e.g., CFI, ASK-Back).

**Fields**

* `code` (CharField): Unique code.
* `name` (CharField)
* `icon` (ImageField, optional)
* `applies_to` (CharField): 'student', 'rated', or 'both'.
* `is_obsolete` (BooleanField)
* `tooltip` (TextField, optional)

**Methods**

* `__str__()`: Returns `name`.

---

## MemberQualification

Tracks assignment of `ClubQualificationType` to a `Member`.

**Fields**

* `member` (ForeignKey → Member)
* `qualification` (ForeignKey → ClubQualificationType)
* `is_qualified` (BooleanField)
* `instructor` (ForeignKey → Member, optional)
* `date_awarded`, `expiration_date` (DateField, optional)
* `notes` (TextField, optional)
* `imported` (BooleanField): Legacy import flag.

**Meta**

* `unique_together = ('member', 'qualification')`

**Methods**

* `__str__()`: Returns `"{member} – {qualification.code}"`.

---

## StudentProgressSnapshot

Precomputed progress summary for dashboard performance.

**Fields**

* `student` (OneToOneField → Member)
* `solo_progress` (FloatField): 0.0–1.0 fraction of solo lessons done.
* `checkride_progress` (FloatField): 0.0–1.0 fraction of rating lessons done.
* `sessions` (IntegerField): Total count of flight + ground sessions.
* `last_updated` (DateTimeField): Auto‑updated timestamp.

**Methods**

* `__str__()`: Returns `"Progress for {student.full_display_name}"`.
