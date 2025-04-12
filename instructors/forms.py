from django import forms
from django.forms import modelformset_factory
from .models import InstructionReport, LessonScore, TrainingLesson

class InstructionReportForm(forms.ModelForm):
    class Meta:
        model = InstructionReport
        fields = ["report_text"]
        widgets = {
            "report_text": forms.Textarea(attrs={"rows": 6, "class": "form-control"}),
        }

class LessonScoreForm(forms.ModelForm):
    class Meta:
        model = LessonScore
        fields = ["lesson", "score", "notes"]
        widgets = {
            "score": forms.Select(attrs={"class": "form-select"}),
            "notes": forms.Textarea(attrs={"rows": 2, "class": "form-control"}),
        }

LessonScoreFormSet = modelformset_factory(
    LessonScore,
    form=LessonScoreForm,
    extra=0,
    can_delete=False
)
