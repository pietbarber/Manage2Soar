from django.contrib import admin
from reversion.admin import VersionAdmin
from tinymce.models import HTMLField
from tinymce.widgets import TinyMCE
from utils.admin_helpers import AdminHelperMixin

from .models import (
    ClubQualificationType,
    GroundInstruction,
    GroundLessonScore,
    InstructionReport,
    LessonScore,
    MemberQualification,
    SyllabusDocument,
    TrainingLesson,
    TrainingPhase,
)

####################################################
# TrainingLessonAdmin
#
# Admin interface for TrainingLesson model using reversion.
# - list_display: 'code', 'title', 'far_requirement', 'pts_reference'
# - list_filter: 'far_requirement', 'pts_reference'
# - search_fields: 'code', 'title', 'description'
# - ordering: 'code'
####################################################


@admin.register(TrainingLesson)
class TrainingLessonAdmin(AdminHelperMixin, VersionAdmin):
    list_display = ("code", "title", "far_requirement", "pts_reference")
    list_filter = ("far_requirement", "pts_reference")
    search_fields = ("code", "title", "description")
    ordering = ("code",)

    admin_helper_message = (
        "Training lessons: syllabus content for instruction. Edit lesson HTML carefully; used in student progress reports."
    )


####################################################
# TrainingPhaseAdmin
#
# Admin interface for TrainingPhase model using reversion.
# - list_display: 'number', 'name'
# - ordering: 'number'
####################################################


@admin.register(TrainingPhase)
class TrainingPhaseAdmin(AdminHelperMixin, VersionAdmin):
    list_display = ("number", "name")
    ordering = ("number",)

    admin_helper_message = (
        "Training phases: group lessons into phases; changing order affects syllabus structure."
    )


####################################################
# SyllabusDocumentAdmin
#
# Admin interface for SyllabusDocument model using reversion.
# - list_display: 'slug', 'title'
# - search_fields: 'slug', 'title', 'content'
# - formfield_overrides: TinyMCE widget for HTMLField
####################################################


@admin.register(SyllabusDocument)
class SyllabusDocumentAdmin(AdminHelperMixin, VersionAdmin):
    list_display = ("slug", "title")
    search_fields = ("slug", "title", "content")
    formfield_overrides = {
        # apply only to HTMLField fields
        HTMLField: {
            "widget": TinyMCE(
                mce_attrs={
                    "relative_urls": False,  # prevent ugly ../../../ paths
                    "remove_script_host": True,
                    # disable URL conversion to preserve user input (fixes issue #207)
                    "convert_urls": False,
                }
            )
        },
    }

    admin_helper_message = (
        "Syllabus docs: HTML documents used in training pages. Use TinyMCE for content edits."
    )


####################################################
# LessonScoreInline
#
# Inline for editing LessonScore objects within InstructionReport admin.
# - model: LessonScore
# - extra: 0
####################################################


class LessonScoreInline(admin.TabularInline):
    model = LessonScore
    extra = 0


####################################################
# InstructionReportAdmin
#
# Admin interface for InstructionReport model.
# - list_display: 'student', 'instructor', 'report_date'
# - list_filter: 'report_date', 'instructor'
# - search_fields: 'student__last_name', 'instructor__last_name'
# - inlines: [LessonScoreInline]
####################################################


@admin.register(InstructionReport)
class InstructionReportAdmin(AdminHelperMixin, admin.ModelAdmin):
    list_display = ("student", "instructor", "report_date")
    list_filter = ("report_date", "instructor")
    search_fields = ("student__last_name", "instructor__last_name")
    inlines = [LessonScoreInline]

    admin_helper_message = (
        "Instruction reports: instructor evaluations for students. Reports are audited and used for qualifications."
    )


####################################################
# LessonScoreAdmin
#
# Admin interface for LessonScore model.
# - list_display: 'report', 'lesson', 'score'
# - list_filter: 'lesson', 'score'
####################################################


@admin.register(LessonScore)
class LessonScoreAdmin(AdminHelperMixin, admin.ModelAdmin):
    list_display = ("report", "lesson", "score")
    list_filter = ("lesson", "score")

    admin_helper_message = (
        "Lesson scores: link training lessons to reports. Use inlines on reports for editing."
    )


####################################################
# GroundLessonScoreInline
#
# Inline for editing GroundLessonScore objects within GroundInstruction admin.
# - model: GroundLessonScore
# - extra: 0
####################################################


class GroundLessonScoreInline(admin.TabularInline):
    model = GroundLessonScore
    extra = 0


####################################################
# GroundInstructionAdmin
#
# Admin interface for GroundInstruction model.
# - list_display: 'student', 'instructor', 'date', 'location', 'duration'
# - list_filter: 'date', 'instructor'
# - search_fields: student and instructor names
# - inlines: [GroundLessonScoreInline]
####################################################


@admin.register(GroundInstruction)
class GroundInstructionAdmin(AdminHelperMixin, admin.ModelAdmin):
    list_display = ("student", "instructor", "date", "location", "duration")
    list_filter = ("date", "instructor")
    search_fields = (
        "student__first_name",
        "student__last_name",
        "instructor__first_name",
        "instructor__last_name",
    )
    inlines = [GroundLessonScoreInline]

    admin_helper_message = (
        "Ground instruction: non-flight sessions such as briefings or simulator time. Records are used in progress calculations."
    )


####################################################
# ClubQualificationTypeAdmin
#
# Admin interface for ClubQualificationType model.
# - list_display: 'code', 'name', 'applies_to', 'is_obsolete'
# - search_fields: 'code', 'name'
# - list_filter: 'applies_to', 'is_obsolete'
# - ordering: 'code'
####################################################


@admin.register(ClubQualificationType)
class ClubQualificationTypeAdmin(AdminHelperMixin, admin.ModelAdmin):
    list_display = ("code", "name", "applies_to", "is_obsolete")
    search_fields = ("code", "name")
    list_filter = ("applies_to", "is_obsolete")
    ordering = ("code",)

    admin_helper_message = (
        "Qualification types: define club qualifications and tooltips. Updates affect member qualifications listings."
    )


####################################################
# MemberQualificationAdmin
#
# Admin interface for MemberQualification model.
# - list_display: 'member', 'qualification', 'is_qualified', 'date_awarded', 'expiration_date', 'imported'
# - search_fields: 'member__username', 'qualification__code'
# - list_filter: 'is_qualified', 'imported', 'qualification__code'
# - autocomplete_fields: 'member', 'qualification', 'instructor'
####################################################


@admin.register(MemberQualification)
class MemberQualificationAdmin(AdminHelperMixin, admin.ModelAdmin):
    list_display = (
        "member",
        "qualification",
        "is_qualified",
        "date_awarded",
        "expiration_date",
        "imported",
    )
    search_fields = ("member__username", "qualification__code")
    list_filter = ("is_qualified", "imported", "qualification__code")
    autocomplete_fields = ("member", "qualification", "instructor")

    admin_helper_message = (
        "Member qualifications: assign or revoke qualifications for members. Prefer issuing via the training workflow."
    )
