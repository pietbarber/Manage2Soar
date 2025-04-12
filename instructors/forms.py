from django import forms
from django.forms import modelformset_factory
from .models import InstructionReport, LessonScore, TrainingLesson
from tinymce.widgets import TinyMCE

class InstructionReportForm(forms.ModelForm):
    class Meta:
        model = InstructionReport
        fields = ["report_text"]
        widgets = {
            "report_text": TinyMCE(attrs={"cols": 80, "rows": 10}),
        }

from instructors.models import TrainingLesson, SCORE_CHOICES

class LessonScoreSimpleForm(forms.Form):
    lesson = forms.ModelChoiceField(queryset=TrainingLesson.objects.all(), widget=forms.HiddenInput())
    score = forms.ChoiceField(
        choices=[("", "---------")] + SCORE_CHOICES,
        required=False,
        widget=forms.Select(attrs={"class": "form-select"})
    )

from django.forms import formset_factory
LessonScoreSimpleFormSet = formset_factory(LessonScoreSimpleForm, extra=0)
