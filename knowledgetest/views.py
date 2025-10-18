import json
import logging

from django.db import transaction
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.generic import DetailView, FormView, ListView, TemplateView, View

from instructors.models import InstructionReport
from knowledgetest.forms import TestBuilderForm, TestSubmissionForm
from knowledgetest.models import (
    Question,
    QuestionCategory,
    WrittenTestAnswer,
    WrittenTestAssignment,
    WrittenTestAttempt,
    WrittenTestTemplate,
    WrittenTestTemplateQuestion,
)
from members.decorators import active_member_required
from notifications.models import Notification

logger = logging.getLogger(__name__)


def _get_empty_preset():
    # This function is called only when needed, preventing database queries at import time.
    codes = Question.objects.values_list("category__code", flat=True)
    return {code: 0 for code in codes}


def get_presets():
    return {
        "ASK21": {
            "ACRO": 0,
            "AIM": 5,
            "AMF": 0,
            "ASK21": 19,
            "DO": 0,
            "Discus": 0,
            "FAR": 5,
            "GF": 10,
            "GFH": 10,
            "GNDOPS": 5,
            "PW5": 0,
            "SSC": 5,
            "ST": 5,
            "WX": 4,
        },
        "PW5": {
            "ACRO": 0,
            "AIM": 5,
            "AMF": 5,
            "ASK21": 0,
            "DO": 0,
            "Discus": 0,
            "FAR": 5,
            "GF": 10,
            "GFH": 10,
            "GNDOPS": 5,
            "PW5": 24,
            "SSC": 5,
            "ST": 5,
            "WX": 4,
        },
        "DISCUS": {
            "ACRO": 0,
            "AIM": 0,
            "AMF": 0,
            "ASK21": 0,
            "DO": 0,
            "Discus": 22,
            "FAR": 5,
            "GF": 10,
            "GFH": 0,
            "GNDOPS": 5,
            "PW5": 0,
            "SSC": 0,
            "ST": 5,
            "WX": 0,
        },
        "ACRO": {"ACRO": 30},
        "EMPTY": _get_empty_preset(),
    }


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
            kw["preset"] = presets.get(preset.upper())
        else:
            kw["preset"] = None  # Or a default preset if applicable
        return kw

    def get_context_data(self, **ctx):
        ctx = super().get_context_data(**ctx)
        presets = get_presets()
        ctx["presets"] = presets.keys()
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
        weights = {}
        codes = QuestionCategory.objects.values_list("code", flat=True)
        for code in codes:
            val = data.get(f"weight_{code}")
            if val and val > 0:
                weights[code] = val
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
                    qs = list(
                        Question.objects.filter(category__code=code).exclude(
                            qnum__in=must
                        )
                    )
                    if cnt:
                        pool.extend(qs * cnt)
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
        # Build a breakdown of how many questions per category were on this test
        from django.db.models import Count

        breakdown_qs = attempt.answers.values("question__category__code").annotate(
            num=Count("pk")
        )
        breakdown = [
            f"{entry['question__category__code']} ({entry['num']})"
            for entry in breakdown_qs
        ]
        breakdown_txt = ", ".join(breakdown)

        # 1) Mark any assignment complete
        try:
            asn = WrittenTestAssignment.objects.get(
                template=tmpl, student=request.user, completed=False
            )
            asn.attempt = attempt
            asn.completed = True
            asn.save(update_fields=["attempt", "completed"])
        except WrittenTestAssignment.DoesNotExist:
            pass

        # 2) Log into InstructionReport, using the instructor who created the test
        proctor = tmpl.created_by
        if proctor:
            # build a subject‐count breakdown
            from django.db.models import Count

            breakdown_qs = attempt.answers.values("question__category__code").annotate(
                num=Count("pk")
            )
            breakdown_list = [
                f"{entry['question__category__code']} ({entry['num']})"
                for entry in breakdown_qs
            ]
            breakdown_txt = ", ".join(breakdown_list)

            # Build a compact report_text in pieces to keep source lines short.
            outcome = "Passed" if attempt.passed else "Failed"
            pct = f"{attempt.score_percentage:.0f}%"
            report_text = (
                "Written test \"" + str(tmpl.name) + "\" completed: "
                + pct
                + " ("
                + outcome
                + "). Subject breakdown: "
                + breakdown_txt
                + "."
            )
            InstructionReport.objects.create(
                student=request.user,
                instructor=proctor,
                report_date=timezone.now().date(),
                report_text=report_text,
            )
        return redirect("knowledgetest:quiz-result", attempt.pk)


class WrittenTestResultView(DetailView):
    model = WrittenTestAttempt
    template_name = "written_test/result.html"
    context_object_name = "attempt"


class PendingTestsView(ListView):
    template_name = "written_test/pending.html"
    context_object_name = "assignments"

    def get_queryset(self):
        return WrittenTestAssignment.objects.filter(
            student=self.request.user, completed=False
        ).select_related("template")
