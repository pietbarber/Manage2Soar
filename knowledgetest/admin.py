from django.contrib import admin
from django.db import models
from django.utils.html import format_html
from tinymce.widgets import TinyMCE

from utils.admin_helpers import AdminHelperMixin

from .models import (
    Question,
    QuestionCategory,
    TestPreset,
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

    @admin.display(description="Assigned To")
    def assigned_to(self, obj):
        # Show the full display name for each assigned student
        students = [
            assignment.student.full_display_name for assignment in obj.assignments.all()
        ]
        return ", ".join(students) if students else "-"

    admin_helper_message = "Test templates: define question sets and assignments. Editing templates affects future attempts."


@admin.register(QuestionCategory)
class QuestionCategoryAdmin(AdminHelperMixin, admin.ModelAdmin):
    list_display = ["code", "description"]
    search_fields = ["code", "description"]

    admin_helper_message = "Question categories: organize knowledge test questions. Keep codes stable for reporting."


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

    @admin.display(description="Question")
    def short_question(self, obj):
        return format_html("{}...", obj.question_text[:50])

    @admin.display(description="Attachment")
    def media_preview(self, obj):
        if obj.media:
            return format_html(
                '<a href="{}" target="_blank">View Media</a>', obj.media.url
            )
        return "-"

    admin_helper_message = "Questions: edit or add knowledge-test questions. Use attachments for diagrams or media."


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

    admin_helper_message = "Test attempts: read-only records of student attempts. Use for grading audits and support."


@admin.register(WrittenTestAnswer)
class WrittenTestAnswerAdmin(AdminHelperMixin, admin.ModelAdmin):
    list_display = ["attempt", "question", "selected_answer", "is_correct"]
    list_filter = ["is_correct"]
    search_fields = ["attempt__student__username"]
    readonly_fields = ["attempt", "question", "selected_answer", "is_correct"]

    admin_helper_message = (
        "Attempt answers: read-only details of student responses for each attempt."
    )


@admin.register(TestPreset)
class TestPresetAdmin(AdminHelperMixin, admin.ModelAdmin):
    list_display = (
        "name",
        "description_preview",
        "total_questions",
        "is_active",
        "sort_order",
        "created_at",
    )
    list_editable = ("is_active", "sort_order")
    list_filter = ("is_active", "created_at")
    search_fields = ("name", "description")
    ordering = ("sort_order", "name")

    fieldsets = (
        (None, {"fields": ("name", "description", "is_active", "sort_order")}),
        (
            "Question Weights",
            {
                "fields": ("category_weights", "formatted_weights"),
                "description": "Configure how many questions from each category to include in tests using this preset.",
            },
        ),
        (
            "Timestamps",
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )

    readonly_fields = ("created_at", "updated_at", "formatted_weights")

    @admin.display(description="Description")
    def description_preview(self, obj):
        """Show truncated description in list view."""
        if obj.description:
            return obj.description[:50] + ("..." if len(obj.description) > 50 else "")
        return "-"

    @admin.display(description="Total Questions")
    def total_questions(self, obj):
        """Show total number of questions in this preset."""
        return obj.get_total_questions()

    @admin.display(description="Question Distribution")
    def formatted_weights(self, obj):
        """Display category weights in a readable format."""
        if not obj.category_weights:
            return "No questions configured"

        # Get categories for context
        from .models import QuestionCategory

        categories = {
            cat.code: cat.description for cat in QuestionCategory.objects.all()
        }

        formatted_items = []
        for code, weight in obj.category_weights.items():
            if weight > 0:
                desc = categories.get(code, code)
                formatted_items.append(f"{desc} ({code}): {weight}")

        return (
            format_html("<br>".join(formatted_items))
            if formatted_items
            else "No questions configured"
        )

    def _has_preset_permission(self, request, allow_cfi: bool = True):
        """
        Helper for preset permissions.
        Webmaster and superuser always allowed.
        Chief Flight Instructor allowed only if allow_cfi is True.
        """
        user = request.user
        if user.is_superuser or user.groups.filter(name="Webmasters").exists():
            return True
        if allow_cfi and user.groups.filter(name="Chief Flight Instructor").exists():
            return True
        return False

    def has_change_permission(self, request, obj=None):
        # Only allow Webmaster, superuser, or Chief Flight Instructor to edit test presets
        return self._has_preset_permission(request, allow_cfi=True)

    def has_add_permission(self, request):
        # Only allow Webmaster, superuser, or Chief Flight Instructor to add test presets
        return self._has_preset_permission(request, allow_cfi=True)

    def has_delete_permission(self, request, obj=None):
        # Only allow Webmaster or superuser to delete test presets
        return self._has_preset_permission(request, allow_cfi=False)

    def delete_model(self, request, obj):
        """Override delete to provide confirmation message."""
        from django.contrib import messages

        super().delete_model(request, obj)
        messages.success(request, f'Successfully deleted test preset "{obj.name}".')

    def delete_queryset(self, request, queryset):
        """Override bulk delete to provide confirmation message."""
        from django.contrib import messages

        # Efficiently get names before deletion using values_list
        deleted_names = list(queryset.values_list("name", flat=True))
        count = queryset.delete()[0]  # delete() returns (count, {model: count})

        if deleted_names:
            messages.success(
                request,
                f'Successfully deleted {count} test presets: {", ".join(deleted_names)}.',
            )
        else:
            messages.success(request, f"Successfully deleted {count} test presets.")

    admin_helper_message = (
        "Test Presets: Configure reusable test templates with predefined question distributions. "
        "Active presets are available when creating new tests. "
        "Sort order controls the display order in the test creation interface. "
        "⚠️ Before deleting presets, manually verify that no existing test templates reference them. "
        "See docs/admin/test-presets.md for manual review procedures."
    )
