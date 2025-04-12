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