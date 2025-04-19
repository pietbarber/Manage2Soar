from django.contrib import admin
from .models import TrainingLesson, TrainingPhase, SyllabusDocument
import reversion
from reversion.admin import VersionAdmin


@admin.register(TrainingLesson)
class TrainingLessonAdmin(VersionAdmin):
    list_display = ("code", "title", "far_requirement", "pts_reference")
    list_filter = ("far_requirement", "pts_reference")
    search_fields = ("code", "title", "description")
    ordering = ("code",)

@admin.register(TrainingPhase)
class TrainingPhaseAdmin(VersionAdmin):
    list_display = ("number", "name")
    ordering = ("number",)

@admin.register(SyllabusDocument)
class SyllabusDocumentAdmin(VersionAdmin):
    list_display = ("slug", "title")
    search_fields = ("slug", "title", "content")

from django.contrib import admin
from .models import InstructionReport, LessonScore

class LessonScoreInline(admin.TabularInline):
    model = LessonScore
    extra = 0

@admin.register(InstructionReport)
class InstructionReportAdmin(admin.ModelAdmin):
    list_display = ("student", "instructor", "report_date")
    list_filter = ("report_date", "instructor")
    search_fields = ("student__last_name", "instructor__last_name")
    inlines = [LessonScoreInline]

@admin.register(LessonScore)
class LessonScoreAdmin(admin.ModelAdmin):
    list_display = ("report", "lesson", "score")
    list_filter = ("lesson", "score")

from .models import GroundInstruction, GroundLessonScore

class GroundLessonScoreInline(admin.TabularInline):
    model = GroundLessonScore
    extra = 0

@admin.register(GroundInstruction)
class GroundInstructionAdmin(admin.ModelAdmin):
    list_display = ("student", "instructor", "date", "location", "duration")
    list_filter = ("date", "instructor")
    search_fields = ("student__first_name", "student__last_name", "instructor__first_name", "instructor__last_name")
    inlines = [GroundLessonScoreInline]

from django.contrib import admin
from .models import ClubQualificationType, MemberQualification

@admin.register(ClubQualificationType)
class ClubQualificationTypeAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'applies_to', 'is_obsolete')
    search_fields = ('code', 'name')
    list_filter = ('applies_to', 'is_obsolete')
    ordering = ('code',)

@admin.register(MemberQualification)
class MemberQualificationAdmin(admin.ModelAdmin):
    list_display = ('member', 'qualification', 'is_qualified', 'date_awarded', 'expiration_date', 'imported')
    search_fields = ('member__username', 'qualification__code')
    list_filter = ('is_qualified', 'imported', 'qualification__code')
    autocomplete_fields = ('member', 'qualification', 'instructor')
