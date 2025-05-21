import json
from django.views.generic import TemplateView, View, DetailView
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.generic import FormView
from django.utils import timezone
from django.views.generic import ListView

from knowledgetest.models import (
    WrittenTestTemplate,
    WrittenTestTemplateQuestion,
    Question,
    WrittenTestAttempt,
    WrittenTestAnswer, 
    QuestionCategory,
    WrittenTestAssignment
)
from knowledgetest.forms import TestSubmissionForm, TestBuilderForm


PRESETS = {

    'ASK21': {
        'ACRO': 0,  'AIM': 5,  'AMF': 0,  'ASK21': 19, 'DO': 0,
        'Discus': 0,'FAR': 5,  'GF': 10, 'GFH': 10,   'GNDOPS':5,
        'PW5': 0,  'SSC': 5,  'ST': 5,  'WX': 4,
    },
    'PW5': {
        'ACRO': 0, 'AIM': 5, 'AMF': 5, 'ASK21': 0, 'DO': 0,
        'Discus': 0,'FAR': 5, 'GF': 10, 'GFH': 10, 'GNDOPS':5,
        'PW5':24,'SSC':5,'ST':5,'WX':4,
    },
    'DISCUS': {
        'ACRO': 0, 'AIM': 0, 'AMF':0, 'ASK21': 0, 'DO': 0,
        'Discus': 22, 'FAR': 5, 'GF': 10, 'GFH': 0, 'GNDOPS' :5,
        'PW5': 0, 'SSC': 0, 'ST': 5, 'WX': 0, 
    },
    'EMPTY': { code: 0 for code in Question.objects.values_list('category__code', flat=True) },
}


class WrittenTestStartView(TemplateView):
    template_name = "written_test/start.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        tmpl = get_object_or_404(WrittenTestTemplate, pk=kwargs['pk'])
        qs = tmpl.questions.all().values(
            'qnum','question_text','option_a','option_b','option_c','option_d'
        )
        ctx['questions']   = list(qs)             # <-- a Python list of dicts
        ctx['submit_url']  = reverse('knowledgetest:quiz-submit', args=[tmpl.pk])
        return ctx


class WrittenTestSubmitView(View):
    def post(self, request, pk):
        tmpl = get_object_or_404(WrittenTestTemplate, pk=pk)
        form = TestSubmissionForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {
                'template': tmpl,
                'questions_json': json.dumps(list(tmpl.questions.all().values(
                    'qnum','question_text','option_a',
                    'option_b','option_c','option_d'
                ))),
                'submit_url': reverse('knowledgetest:quiz-submit', args=[tmpl.pk]),
                'form': form,
            })
        answers = form.cleaned_data['answers']
        attempt = WrittenTestAttempt.objects.create(
            template=tmpl, student=request.user
        )
        correct = 0
        total = tmpl.questions.count()
        for qnum, sel in answers.items():
            q = Question.objects.get(pk=qnum)
            is_corr = (sel == q.correct_answer)
            WrittenTestAnswer.objects.create(
                attempt=attempt,
                question=q,
                selected_answer=sel,
                is_correct=is_corr
            )
            if is_corr:
                correct += 1
        score = (correct / total) * 100 if total else 0
        attempt.score_percentage = score
        attempt.passed = score >= float(tmpl.pass_percentage)

        attempt.save()

        # 1) Mark any assignment complete
        from .models import WrittenTestAssignment
        try:
            asn = WrittenTestAssignment.objects.get(
                template=tmpl, student=request.user, completed=False
            )
            asn.attempt = attempt
            asn.completed = True
            asn.save(update_fields=['attempt','completed'])
        except WrittenTestAssignment.DoesNotExist:
            pass

        # 2) Log into InstructionReport, using the instructor who created the test
        from instructors.models import InstructionReport
        proctor = tmpl.created_by  # this is the instructor who built the template
        if proctor:
            InstructionReport.objects.create(
                student=request.user,
                instructor=proctor,
                report_date=timezone.now().date(),
                report_text=(
                    f'Written test "{tmpl.name}" completed: '
                    f'{attempt.score_percentage:.0f}% '
                    f'({"Passed" if attempt.passed else "Failed"})'
                )
            )

        return redirect('knowledgetest:quiz-result', attempt.pk)

class WrittenTestResultView(DetailView):
    model = WrittenTestAttempt
    template_name = "written_test/result.html"
    context_object_name = 'attempt'


class CreateWrittenTestView(FormView):
    template_name = "written_test/create.html"
    form_class    = TestBuilderForm

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        preset = self.request.GET.get('preset')
        kw['preset'] = PRESETS.get(preset.upper())
        return kw

    def get_context_data(self, **ctx):
        ctx = super().get_context_data(**ctx)
        ctx['presets'] = PRESETS.keys()
        return ctx

    def form_valid(self, form):
        data = form.cleaned_data
        # 1. Pull weights & must_include
        must = []
        if data['must_include']:
            import re
            must = [int(n) for n in re.findall(r'\d+', data['must_include'])]
        weights = {
            code: data[f'weight_{code}']
            for code in QuestionCategory.objects.values_list('code', flat=True)
            if data[f'weight_{code}'] > 0
        }
        total = sum(weights.values())
        if total > 50:
            form.add_error(None, "Cannot select more than 50 questions total.")
            return self.form_invalid(form)

        # 2. Build a template
        tmpl = WrittenTestTemplate.objects.create(
            name=f"Test for {self.request.user} on {timezone.now().date()}",
            pass_percentage=100,  # or pull from form if you want
            created_by=self.request.user
        )

        assignment = WrittenTestAssignment.objects.create(
            template=tmpl,
            student=form.cleaned_data['student'],
            instructor=self.request.user
        )

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
                Question.objects
                        .filter(category__code=code)
                        .exclude(qnum__in=must)
            )
            chosen = random.sample(pool, min(cnt, len(pool)))
            for q in chosen:
                WrittenTestTemplateQuestion.objects.create(
                    template=tmpl, question=q, order=order
                )
                order += 1

        # 5. Redirect to the quiz start
        return redirect(reverse('knowledgetest:quiz-start', args=[tmpl.pk]))


class PendingTestsView(ListView):
    template_name = "written_test/pending.html"
    context_object_name = 'assignments'

    def get_queryset(self):
        return WrittenTestAssignment.objects.filter(
            student=self.request.user,
            completed=False
        ).select_related('template')
