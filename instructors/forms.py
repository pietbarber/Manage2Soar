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

# instructors/forms.py

from django import forms
from instructors.models import GroundInstruction
from members.models import Member
from instructors.models import TrainingLesson
from members.constants.membership import ALLOWED_MEMBERSHIP_STATUSES
class GroundInstructionForm(forms.ModelForm):
    class Meta:
        model = GroundInstruction
        fields = ["student", "date", "location", "duration", "lessons", "notes"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "duration": forms.TimeInput(attrs={"type": "time"}),
            "lessons": forms.CheckboxSelectMultiple,
            "notes": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        instructor = kwargs.pop("instructor", None)
        super().__init__(*args, **kwargs)
        self.fields["student"].queryset = Member.objects.filter(membership_status__in=ALLOWED_MEMBERSHIP_STATUSES)
        self.fields["lessons"].queryset = TrainingLesson.objects.all().order_by("code")
        if instructor:
            self.initial["instructor"] = instructor
