import json
from django.views.generic import TemplateView, View, DetailView
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from knowledgetest.models import (
    WrittenTestTemplate,
    Question,
    WrittenTestAttempt,
    WrittenTestAnswer
)
from knowledgetest.forms import TestSubmissionForm

class WrittenTestStartView(TemplateView):
    template_name = "written_test/start.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        tmpl = get_object_or_404(WrittenTestTemplate, pk=kwargs['pk'])
        qs = tmpl.questions.all().values(
            'qnum', 'question_text', 'option_a',
            'option_b', 'option_c', 'option_d'
        )
        ctx.update({
            'template': tmpl,
            'questions_json': json.dumps(list(qs)),
            'submit_url': reverse('knowledgetest:quiz-submit', args=[tmpl.pk]),
        })
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
        return redirect('knowledgetest:quiz-result', attempt.pk)

class WrittenTestResultView(DetailView):
    model = WrittenTestAttempt
    template_name = "written_test/result.html"
    context_object_name = 'attempt'
