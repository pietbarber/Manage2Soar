from django.contrib import admin
from django.db import models
from django.utils.html import format_html
from tinymce.widgets import TinyMCE

from .models import (
    QuestionCategory,
    Question,
    WrittenTestTemplate,
    WrittenTestTemplateQuestion,
    WrittenTestAttempt,
    WrittenTestAnswer
)

# Inline for template-question relationship
class TemplateQuestionInline(admin.TabularInline):
    model = WrittenTestTemplateQuestion
    extra = 1
    autocomplete_fields = ['question']
    fields = ['question', 'order']

@admin.register(WrittenTestTemplate)
class WrittenTestTemplateAdmin(admin.ModelAdmin):
    list_display = ['name', 'pass_percentage', 'time_limit', 'created_by', 'created_at']
    search_fields = ['name', 'description']
    list_filter = ['pass_percentage']
    inlines = [TemplateQuestionInline]

@admin.register(QuestionCategory)
class QuestionCategoryAdmin(admin.ModelAdmin):
    list_display = ['code', 'description']
    search_fields = ['code', 'description']

@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ['qnum', 'category', 'short_question', 'correct_answer', 'last_updated']
    list_filter = ['category']
    search_fields = ['question_text', 'explanation']
    readonly_fields = ['media_preview']
    formfield_overrides = {
        models.TextField: {'widget': TinyMCE(attrs={'cols': 80, 'rows': 10})},
    }

    def short_question(self, obj):
        return format_html("{}...", obj.question_text[:50])
    short_question.short_description = 'Question'

    def media_preview(self, obj):
        if obj.media:
            return format_html('<a href="{}" target="_blank">View Media</a>', obj.media.url)
        return '-'
    media_preview.short_description = 'Attachment'

# Inline for attempt answers
class AnswerInline(admin.TabularInline):
    model = WrittenTestAnswer
    extra = 0
    readonly_fields = ['question', 'selected_answer', 'is_correct']
    can_delete = False

@admin.register(WrittenTestAttempt)
class WrittenTestAttemptAdmin(admin.ModelAdmin):
    list_display = ['student', 'template', 'date_taken', 'score_percentage', 'passed']
    list_filter = ['template', 'passed']
    search_fields = ['student__username']
    readonly_fields = ['student', 'template', 'date_taken', 'score_percentage', 'passed', 'time_taken']
    inlines = [AnswerInline]

@admin.register(WrittenTestAnswer)
class WrittenTestAnswerAdmin(admin.ModelAdmin):
    list_display = ['attempt', 'question', 'selected_answer', 'is_correct']
    list_filter = ['is_correct']
    search_fields = ['attempt__student__username']
    readonly_fields = ['attempt', 'question', 'selected_answer', 'is_correct']
