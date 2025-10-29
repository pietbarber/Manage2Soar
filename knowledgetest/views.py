import json
import logging

from django.db import transaction
from django.http import HttpResponseForbidden, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.html import format_html
from django.views.generic import DetailView, FormView, ListView, TemplateView, View

from instructors.models import InstructionReport
from knowledgetest.forms import TestBuilderForm, TestSubmissionForm
from knowledgetest.models import (
    Question,
    QuestionCategory,
    TestPreset,
    WrittenTestAnswer,
    WrittenTestAssignment,
    WrittenTestAttempt,
    WrittenTestTemplate,
    WrittenTestTemplateQuestion,
)
from members.decorators import active_member_required
try:
    from notifications.models import Notification
except ImportError:
    # Notifications app may be optional in some deployments; if it's not
    # available, fall back to None and make notification-related code
    # guarded by checks for Notification is not None.
    Notification = None

logger = logging.getLogger(__name__)


def generate_test_subject_breakdown(attempt):
    """
    Generate a human-readable breakdown of test subjects for a WrittenTestAttempt.

    Args:
        attempt: WrittenTestAttempt instance

    Returns:
        str: Formatted breakdown like "Soaring Technique (5), Ground Fundamentals (10)"
    """
    from django.db.models import Count

    breakdown_qs = attempt.answers.values(
        "question__category__code", "question__category__description"
    ).annotate(num=Count("pk"))

    breakdown_list = [
        f"{entry['question__category__description']} ({entry['num']})"
        for entry in breakdown_qs
    ]

    return ", ".join(breakdown_list)


def get_presets():
    """Get test presets from database - maintains compatibility with existing code."""
    return TestPreset.get_presets_as_dict()


class WrittenTestStartView(TemplateView):
    template_name = "written_test/start.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        tmpl = get_object_or_404(WrittenTestTemplate, pk=kwargs["pk"])
        qs = tmpl.questions.all().values(
            # from knowledgetest.views import get_presets
        )
        ctx["questions"] = list(qs)  # <-- a Python list of dicts
        ctx["submit_url"] = reverse("knowledgetest:quiz-submit", args=[tmpl.pk])
        return ctx


# ################################################################
# Helper mixin to enforce “only the assigned student or staff”
# ################################################################


class AssignmentPermissionMixin:
    def dispatch(self, request, *args, **kwargs):
        # Must be logged in
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        template_id = kwargs.get("pk")
        # Check for an assignment
        is_owner = WrittenTestAssignment.objects.filter(
            template_id=template_id, student=request.user
        ).exists()
        # Allow staff (or superusers) too
        if not is_owner and not request.user.is_staff:
            return HttpResponseForbidden("You’re not allowed to take this test.")

        return super().dispatch(request, *args, **kwargs)


# ################################################################
# Secure the Start View
# ################################################################
@method_decorator(active_member_required, name="dispatch")
class CreateWrittenTestView(FormView):
    template_name = "written_test/create.html"
    form_class = TestBuilderForm

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        preset = self.request.GET.get("preset")
        if preset:
            presets = get_presets()
            kw["preset"] = presets.get(preset)
        else:
            kw["preset"] = None  # Or a default preset if applicable
        return kw

    def get_context_data(self, **ctx):
        ctx = super().get_context_data(**ctx)
        # Load active presets from database
        active_presets = TestPreset.get_active_presets()
        ctx["presets"] = [preset.name for preset in active_presets]
        # For template access to descriptions, etc.
        ctx["preset_objects"] = active_presets
        return ctx

    def form_invalid(self, form):
        return super().form_invalid(form)

    def form_valid(self, form):
        data = form.cleaned_data
        # 1. Pull weights & must_include
        must = []
        if data["must_include"]:
            import re

            must = [int(n) for n in re.findall(r"\d+", data["must_include"])]
        weights = {
            code: data[f"weight_{code}"]
            for code in QuestionCategory.objects.values_list("code", flat=True)
            if data[f"weight_{code}"] > 0
        }
        total = sum(weights.values())
        MAX_QUESTIONS = 50
        import random

        # If too many, randomly select down to 50 (must-includes always included)
        if total + len(must) > MAX_QUESTIONS:
            # Remove duplicates in must
            must = list(dict.fromkeys(must))
            if len(must) >= MAX_QUESTIONS:
                must = must[:MAX_QUESTIONS]
                weights = {}
            else:
                # Build a pool of all possible (non-must) questions
                pool = []
                for code, cnt in weights.items():
                    pool.extend(
                        list(
                            Question.objects.filter(category__code=code).exclude(
                                qnum__in=must
                            )
                        )
                        * cnt
                    )
                # Remove duplicates and already-included
                pool = list({q.qnum: q for q in pool}.values())
                needed = MAX_QUESTIONS - len(must)
                chosen = random.sample(pool, min(needed, len(pool)))
                # Overwrite weights to only include chosen
                weights = {}
                for q in chosen:
                    weights.setdefault(q.category.code, 0)
                    weights[q.category.code] += 1
                # Now must is capped, and weights is capped

        # 2. Build a template
        with transaction.atomic():
            tmpl = WrittenTestTemplate.objects.create(
                name=f"Test by {self.request.user} on {timezone.now().date()}",
                description=data.get("description", ""),
                pass_percentage=data["pass_percentage"],
                created_by=self.request.user,
            )
            WrittenTestAssignment.objects.create(
                template=tmpl, student=data["student"], instructor=self.request.user
            )
        # Create notification for the student
        try:
            if Notification is not None:
                Notification.objects.create(
                    user=data["student"],
                    message=f"You have been assigned a new written test: {tmpl.name}",
                    url=reverse("knowledgetest:quiz-pending"),
                )
        except Exception:
            pass
        order = 1
        # 3. First, include forced questions
        for qnum in must:
            try:
                q = Question.objects.get(pk=qnum)
                WrittenTestTemplateQuestion.objects.create(
                    template=tmpl, question=q, order=order
                )
                order += 1
            except Question.DoesNotExist:
                continue

        # 4. Then, for each category, randomly choose unanswered ones
        import random

        for code, cnt in weights.items():
            pool = list(
                Question.objects.filter(category__code=code).exclude(qnum__in=must)
            )
            chosen = random.sample(pool, min(cnt, len(pool)))
            for q in chosen:
                WrittenTestTemplateQuestion.objects.create(
                    template=tmpl, question=q, order=order
                )
                order += 1

        # 5. Redirect to the quiz start
        return redirect(reverse("knowledgetest:quiz-start", args=[tmpl.pk]))


# ################################################################
# Secure the Submit View
# ################################################################
@method_decorator(active_member_required, name="dispatch")
class WrittenTestSubmitView(View):
    template_name = "written_test/start.html"

    def post(self, request, pk):
        tmpl = get_object_or_404(WrittenTestTemplate, pk=pk)
        form = TestSubmissionForm(request.POST)
        if not form.is_valid():
            form.add_error(None, "Invalid answer payload")
            return render(
                request,
                self.template_name,
                {
                    "template": tmpl,
                    "questions_json": json.dumps(
                        list(
                            tmpl.questions.all().values(
                                "qnum",
                                "question_text",
                                "option_a",
                                "option_b",
                                "option_c",
                                "option_d",
                            )
                        )
                    ),
                    "submit_url": reverse("knowledgetest:quiz-submit", args=[tmpl.pk]),
                    "form": form,
                },
            )
        answers = form.cleaned_data["answers"]
        attempt = WrittenTestAttempt.objects.create(template=tmpl, student=request.user)
        correct = 0
        total = tmpl.questions.count()
        for qnum, sel in answers.items():
            q = Question.objects.get(pk=qnum)
            is_corr = sel == q.correct_answer
            WrittenTestAnswer.objects.create(
                attempt=attempt, question=q, selected_answer=sel, is_correct=is_corr
            )
            if is_corr:
                correct += 1
        score = (correct / total) * 100 if total else 0
        attempt.score_percentage = score
        attempt.passed = score >= float(tmpl.pass_percentage)

        attempt.save()
        # Build a URL to the attempt result so we can reuse it for notifications
        try:
            notif_url = reverse("knowledgetest:quiz-result", args=[attempt.pk])
        except Exception:
            notif_url = None
        # Build a breakdown of how many questions per category were on this test
        breakdown_txt = generate_test_subject_breakdown(attempt)

        # 1) Mark any assignment complete
        try:
            asn = WrittenTestAssignment.objects.get(
                template=tmpl, student=request.user, completed=False
            )
            asn.attempt = attempt
            asn.completed = True
            asn.save(update_fields=["attempt", "completed"])
            # Notify the assigning instructor (if any) and the test creator/proctor
            try:
                if Notification is not None:
                    student_name = getattr(
                        request.user, "full_display_name", str(request.user))
                    score_pct = f"{attempt.score_percentage:.0f}%" if attempt.score_percentage is not None else "N/A"
                    status = "Passed" if attempt.passed else "Failed"
                    notif_msg = f"{student_name} has completed the written test '{tmpl.name}': {score_pct} ({status})."
                    # notif_url computed above

                    if asn.instructor:
                        # Don't crash if creating notification fails
                        try:
                            Notification.objects.create(
                                user=asn.instructor, message=notif_msg, url=notif_url)
                        except Exception:
                            pass

                    # Also notify the proctor/creator if different
                    if tmpl.created_by and tmpl.created_by != asn.instructor:
                        try:
                            Notification.objects.create(
                                user=tmpl.created_by, message=notif_msg, url=notif_url)
                        except Exception:
                            pass
            except Exception:
                # swallow notification errors to avoid breaking test submit
                pass
        except WrittenTestAssignment.DoesNotExist:
            pass

        # 2) Log into InstructionReport, using the instructor who created the test
        proctor = tmpl.created_by
        if proctor:
            # build a subject‐count breakdown
            breakdown_txt = generate_test_subject_breakdown(attempt)

            # Include a persistent link to the attempt result in the report_text
            link_html = (
                format_html(' <a href="{}">View written test result</a>',
                            notif_url) if notif_url else ""
            )
            InstructionReport.objects.create(
                student=request.user,
                instructor=proctor,
                report_date=timezone.now().date(),
                report_text=(
                    f'Written test "{tmpl.name}" completed: '
                    f"{attempt.score_percentage:.0f}% "
                    f'({"Passed" if attempt.passed else "Failed"}). '
                    f"Subject breakdown: {breakdown_txt}." + link_html
                ),
            )
        return redirect("knowledgetest:quiz-result", attempt.pk)


class WrittenTestResultView(DetailView):
    model = WrittenTestAttempt
    template_name = "written_test/result.html"
    context_object_name = "attempt"


@method_decorator(active_member_required, name="dispatch")
class WrittenTestAttemptDeleteView(View):
    """Allow staff, students (own attempts), or the grading instructor/template creator to delete an attempt."""
    template_name = "written_test/delete_confirm.html"

    def _check_permission(self, user, attempt):
        """Check if user can delete this attempt"""
        # Allow staff, the grading instructor, the template creator, or the
        # student who took the attempt to delete their own attempt. Tests rely
        # on students being able to remove their own records in several flows.
        return (
            user.is_staff
            or user == attempt.student
            or (attempt.instructor and attempt.instructor == user)
            or (attempt.template and attempt.template.created_by == user)
        )

    def get(self, request, pk):
        # Allow GET confirmation only for the student who took the test when
        # there is an associated completed assignment (this matches older
        # tests that expect a confirmation page for students). For all other
        # users (including staff), GET is not allowed and should return 405.
        attempt = get_object_or_404(WrittenTestAttempt, pk=pk)
        # Student may view confirmation only when an assignment exists and is completed
        owns_completed_assignment = WrittenTestAssignment.objects.filter(
            template=attempt.template, student=request.user, attempt=attempt, completed=True
        ).exists()
        if request.user == attempt.student and owns_completed_assignment:
            return render(request, self.template_name, {"attempt": attempt})
        return HttpResponseNotAllowed(["POST"])

    def post(self, request, pk):
        attempt = get_object_or_404(WrittenTestAttempt, pk=pk)
        if not self._check_permission(request.user, attempt):
            return HttpResponseForbidden("Not allowed to delete this attempt")
        student_pk = attempt.student.pk
        attempt.delete()
        # Redirect to the student's instruction record where the report lived
        return redirect(reverse("instructors:member_instruction_record", args=[student_pk]))


class PendingTestsView(ListView):
    template_name = "written_test/pending.html"
    context_object_name = "assignments"

    def get_queryset(self):
        return WrittenTestAssignment.objects.filter(
            student=self.request.user, completed=False
        ).select_related("template")


@method_decorator(active_member_required, name="dispatch")
class MemberWrittenTestHistoryView(ListView):
    """Shows all completed written tests for the current member."""
    template_name = "written_test/member_history.html"
    context_object_name = "attempts"
    paginate_by = 20

    def get_queryset(self):
        return WrittenTestAttempt.objects.filter(
            student=self.request.user
        ).select_related(
            "template", "instructor"
        ).prefetch_related(
            "answers__question"
        ).order_by("-date_taken")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Add summary stats
        attempts = self.get_queryset()
        context.update({
            "total_tests": attempts.count(),
            "passed_tests": attempts.filter(passed=True).count(),
            "failed_tests": attempts.filter(passed=False).count(),
        })
        return context


@method_decorator(active_member_required, name="dispatch")
class InstructorRecentTestsView(ListView):
    """Shows recently completed written tests for all students - instructor view."""
    template_name = "written_test/instructor_recent.html"
    context_object_name = "attempts"
    paginate_by = 50

    def dispatch(self, request, *args, **kwargs):
        # Check if user is an instructor (has given instruction reports or is staff)
        if not (request.user.is_staff or
                InstructionReport.objects.filter(instructor=request.user).exists()):
            return HttpResponseForbidden("Access restricted to instructors and staff")
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        # Show tests from the last 30 days, most recent first
        from datetime import timedelta
        cutoff_date = timezone.now() - timedelta(days=30)

        return WrittenTestAttempt.objects.filter(
            date_taken__gte=cutoff_date
        ).select_related(
            "student", "template", "instructor"
        ).order_by("-date_taken")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Add summary stats for the period
        attempts = self.get_queryset()
        context.update({
            "total_recent": attempts.count(),
            "recent_passed": attempts.filter(passed=True).count(),
            "recent_failed": attempts.filter(passed=False).count(),
            "period_days": 30,
        })
        return context
