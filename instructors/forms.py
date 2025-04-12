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

class LessonScoreForm(forms.ModelForm):
    class Meta:
        model = LessonScore
        fields = ["lesson", "score"]
        widgets = {
            "score": forms.Select(attrs={"class": "form-select"}),
        }

LessonScoreFormSet = modelformset_factory(
    LessonScore,
    form=LessonScoreForm,
    extra=0,
    can_delete=False
)
