from django import forms
from django.forms import modelformset_factory
from .models import InstructionReport, LessonScore, TrainingLesson
from tinymce.widgets import TinyMCE

class InstructionReportForm(forms.ModelForm):
    class Meta:
        model = InstructionReport
        fields = ["report_text", "simulator"]
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

from django import forms
from instructors.models import GroundInstruction, GroundLessonScore, TrainingLesson, SCORE_CHOICES
from members.models import Member
from tinymce.widgets import TinyMCE
from django.forms import formset_factory

class GroundInstructionForm(forms.ModelForm):
    class Meta:
        model = GroundInstruction
        fields = ["date", "location", "duration", "notes"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "duration": forms.TextInput(attrs={"placeholder": "HH:MM"}),
            "notes": TinyMCE(attrs={"rows": 6}),
        }

class GroundLessonScoreSimpleForm(forms.Form):
    lesson = forms.IntegerField(widget=forms.HiddenInput())
    score = forms.ChoiceField(
        choices=[("", "---------")] + SCORE_CHOICES,
        required=False,
        widget=forms.Select(attrs={"class": "form-select"})
    )

GroundLessonScoreFormSet = formset_factory(
    GroundLessonScoreSimpleForm,
    extra=0,
    can_delete=False,
    validate_min=False,
    validate_max=False
)
