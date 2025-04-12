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
    list_display = ("report", "lesson", "score", "notes")
    list_filter = ("lesson", "score")
    search_fields = ("notes",)
