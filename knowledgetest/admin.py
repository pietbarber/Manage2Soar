from django.contrib import admin
from django.db import models
from django.utils.html import format_html
from tinymce.widgets import TinyMCE
from utils.admin_helpers import AdminHelperMixin

from .models import (
    Question,
    QuestionCategory,
    WrittenTestAnswer,
    WrittenTestAttempt,
    WrittenTestTemplate,
    WrittenTestTemplateQuestion,
)


# Inline for template-question relationship
class TemplateQuestionInline(admin.TabularInline):
    model = WrittenTestTemplateQuestion
    extra = 1
    autocomplete_fields = ["question"]
    fields = ["question", "order"]


@admin.register(WrittenTestTemplate)
class WrittenTestTemplateAdmin(AdminHelperMixin, admin.ModelAdmin):
    list_display = [
        "name",
        "pass_percentage",
        "assigned_to",
        "created_by",
        "created_at",
    ]
    search_fields = ["name", "description"]
    list_filter = ["pass_percentage"]
    inlines = [TemplateQuestionInline]

    def assigned_to(self, obj):
        # Show the full display name for each assigned student
        students = [
            assignment.student.full_display_name for assignment in obj.assignments.all()
        ]
        return ", ".join(students) if students else "-"

    assigned_to.short_description = "Assigned To"

    admin_helper_message = (
        "Test templates: define question sets and assignments. Editing templates affects future attempts."
    )


@admin.register(QuestionCategory)
class QuestionCategoryAdmin(AdminHelperMixin, admin.ModelAdmin):
    list_display = ["code", "description"]
    search_fields = ["code", "description"]

    admin_helper_message = (
        "Question categories: organize knowledge test questions. Keep codes stable for reporting."
    )


@admin.register(Question)
class QuestionAdmin(AdminHelperMixin, admin.ModelAdmin):
    list_display = [
        "qnum",
        "category",
        "short_question",
        "correct_answer",
        "last_updated",
    ]
    list_filter = ["category"]
    search_fields = ["question_text", "explanation"]
    readonly_fields = ["media_preview"]
    formfield_overrides = {
        models.TextField: {"widget": TinyMCE(attrs={"cols": 80, "rows": 10})},
    }

    def short_question(self, obj):
        return format_html("{}...", obj.question_text[:50])

    short_question.short_description = "Question"

    def media_preview(self, obj):
        if obj.media:
            return format_html(
                '<a href="{}" target="_blank">View Media</a>', obj.media.url
            )
        return "-"

    media_preview.short_description = "Attachment"

    admin_helper_message = (
        "Questions: edit or add knowledge-test questions. Use attachments for diagrams or media."
    )


# Inline for attempt answers
class AnswerInline(admin.TabularInline):
    model = WrittenTestAnswer
    extra = 0
    readonly_fields = ["question", "selected_answer", "is_correct"]
    can_delete = False


@admin.register(WrittenTestAttempt)
class WrittenTestAttemptAdmin(AdminHelperMixin, admin.ModelAdmin):
    list_display = ["student", "template", "date_taken", "score_percentage", "passed"]
    list_filter = ["template", "passed"]
    search_fields = ["student__username"]
    readonly_fields = [
        "student",
        "template",
        "date_taken",
        "score_percentage",
        "passed",
        "time_taken",
    ]
    inlines = [AnswerInline]

    admin_helper_message = (
        "Test attempts: read-only records of student attempts. Use for grading audits and support."
    )


@admin.register(WrittenTestAnswer)
class WrittenTestAnswerAdmin(AdminHelperMixin, admin.ModelAdmin):
    list_display = ["attempt", "question", "selected_answer", "is_correct"]
    list_filter = ["is_correct"]
    search_fields = ["attempt__student__username"]
    readonly_fields = ["attempt", "question", "selected_answer", "is_correct"]

    admin_helper_message = (
        "Attempt answers: read-only details of student responses for each attempt."
    )
