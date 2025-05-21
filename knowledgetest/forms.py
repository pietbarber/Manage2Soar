from django import forms
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
