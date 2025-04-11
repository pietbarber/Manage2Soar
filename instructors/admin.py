from django.contrib import admin
from .models import TrainingLesson

@admin.register(TrainingLesson)
class TrainingLessonAdmin(admin.ModelAdmin):
    list_display = ("code", "title", "far_requirement", "pts_reference")
    list_filter = ("far_requirement", "pts_reference")
    search_fields = ("code", "title", "description")
    ordering = ("code",)
