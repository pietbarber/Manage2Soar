from django.contrib import admin
from .models import TrainingLesson, TrainingPhase, SyllabusDocument

@admin.register(TrainingLesson)
class TrainingLessonAdmin(admin.ModelAdmin):
    list_display = ("code", "title", "far_requirement", "pts_reference")
    list_filter = ("far_requirement", "pts_reference")
    search_fields = ("code", "title", "description")
    ordering = ("code",)

@admin.register(TrainingPhase)
class TrainingPhaseAdmin(admin.ModelAdmin):
    list_display = ("number", "name")
    ordering = ("number",)

@admin.register(SyllabusDocument)
class SyllabusDocumentAdmin(admin.ModelAdmin):
    list_display = ("slug", "title")
    search_fields = ("slug", "title", "content")