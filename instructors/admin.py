from django.contrib import admin
from reversion.admin import VersionAdmin
from tinymce.models import HTMLField
from tinymce.widgets import TinyMCE

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
class TrainingLessonAdmin(VersionAdmin):
    list_display = ("code", "title", "far_requirement", "pts_reference")
    list_filter = ("far_requirement", "pts_reference")
    search_fields = ("code", "title", "description")
    ordering = ("code",)


####################################################
# TrainingPhaseAdmin
#
# Admin interface for TrainingPhase model using reversion.
# - list_display: 'number', 'name'
# - ordering: 'number'
####################################################


@admin.register(TrainingPhase)
class TrainingPhaseAdmin(VersionAdmin):
    list_display = ("number", "name")
    ordering = ("number",)


####################################################
# SyllabusDocumentAdmin
#
# Admin interface for SyllabusDocument model using reversion.
# - list_display: 'slug', 'title'
# - search_fields: 'slug', 'title', 'content'
# - formfield_overrides: TinyMCE widget for HTMLField
####################################################


@admin.register(SyllabusDocument)
class SyllabusDocumentAdmin(VersionAdmin):
    list_display = ("slug", "title")
    search_fields = ("slug", "title", "content")
    formfield_overrides = {
        # apply only to HTMLField fields
        HTMLField: {
            "widget": TinyMCE(
                mce_attrs={
                    "relative_urls": False,
                    "remove_script_host": True,
                    "convert_urls": True,
                }
            )
        },
    }


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
class InstructionReportAdmin(admin.ModelAdmin):
    list_display = ("student", "instructor", "report_date")
    list_filter = ("report_date", "instructor")
    search_fields = ("student__last_name", "instructor__last_name")
    inlines = [LessonScoreInline]


####################################################
# LessonScoreAdmin
#
# Admin interface for LessonScore model.
# - list_display: 'report', 'lesson', 'score'
# - list_filter: 'lesson', 'score'
####################################################


@admin.register(LessonScore)
class LessonScoreAdmin(admin.ModelAdmin):
    list_display = ("report", "lesson", "score")
    list_filter = ("lesson", "score")


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
class GroundInstructionAdmin(admin.ModelAdmin):
    list_display = ("student", "instructor", "date", "location", "duration")
    list_filter = ("date", "instructor")
    search_fields = (
        "student__first_name",
        "student__last_name",
        "instructor__first_name",
        "instructor__last_name",
    )
    inlines = [GroundLessonScoreInline]


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
class ClubQualificationTypeAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "applies_to", "is_obsolete")
    search_fields = ("code", "name")
    list_filter = ("applies_to", "is_obsolete")
    ordering = ("code",)


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
class MemberQualificationAdmin(admin.ModelAdmin):
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
