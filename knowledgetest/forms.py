from django import forms
from knowledgetest.models import QuestionCategory
import json

class TestSubmissionForm(forms.Form):
    answers = forms.CharField(widget=forms.HiddenInput)

    def clean_answers(self):
        data = self.cleaned_data['answers']
        try:
            answers = json.loads(data)
        except json.JSONDecodeError:
            raise forms.ValidationError("Invalid answer payload.")
        cleaned = {}
        for k, v in answers.items():
            try:
                qnum = int(k)
            except ValueError:
                raise forms.ValidationError(f"Bad question number: {k}")
            if v not in ('A', 'B', 'C', 'D'):
                raise forms.ValidationError(f"Bad choice for Q{qnum}: {v}")
            cleaned[qnum] = v
        return cleaned

class TestBuilderForm(forms.Form):
    must_include = forms.CharField(
        widget=forms.Textarea(attrs={'rows':3, 'class':'form-control'}),
        required=False,
        help_text="Type Q-numbers (comma/space separated) to force-include"
    )
    
    def __init__(self, *args, preset=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Dynamically add a “weight” field for each category
        for cat in QuestionCategory.objects.all():
            self.fields[f'weight_{cat.code}'] = forms.IntegerField(
                label=f"{cat.code} ({cat.description})",
                min_value=0,
                max_value=cat.question_set.count(),
                initial=(preset or {}).get(cat.code, 0),
                widget=forms.Select(
                   choices=[(i,i) for i in range(cat.question_set.count()+1)],
                   attrs={'class':'form-select'}
                )
            )
