import json

from django import forms

from knowledgetest.models import QuestionCategory
from members.models import Member


class TestSubmissionForm(forms.Form):
    answers = forms.CharField(widget=forms.HiddenInput)

    def clean_answers(self):
        data = self.cleaned_data["answers"]
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
            if v not in ("A", "B", "C", "D"):
                raise forms.ValidationError(f"Bad choice for Q{qnum}: {v}")
            cleaned[qnum] = v
        return cleaned


class TestBuilderForm(forms.Form):
    description = forms.CharField(
        label="Test Description",
        widget=forms.Textarea(
            attrs={
                "rows": 2,
                "class": "form-control mb-3",
                "placeholder": "e.g. ASK-21 test, Pre-solo written, Duty Officer Responsibilities, etc.",
            }
        ),
        required=False,
        help_text="A short description or title for this test.",
    )
    student = forms.ModelChoiceField(
        queryset=Member.objects.filter(is_active=True).order_by(
            "last_name", "first_name"
        ),
        label="Assign test to",
        required=True,
        error_messages={"required": "Please select a club member to assign this test."},
        widget=forms.Select(
            attrs={"class": "form-select mb-3", "required": "required"}
        ),
        help_text="Select the club member who will take this test",
    )
    pass_percentage = forms.DecimalField(
        max_digits=5,
        decimal_places=2,
        initial=100,
        min_value=0,
        max_value=100,
        label="Pass Percentage",
        help_text="Minimum % score required to pass",
    )
    must_include = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3, "class": "form-control mb-3"}),
        required=False,
        help_text="Q-numbers to force-include (comma/space separated)",
    )

    def __init__(self, *args, **kwargs):
        preset = kwargs.pop("preset", None)
        super().__init__(*args, **kwargs)
        # dynamically add weight field for each category
        for cat in QuestionCategory.objects.all():
            self.fields[f"weight_{cat.code}"] = forms.IntegerField(
                label=f"{cat.code} ({cat.description})",
                min_value=0,
                max_value=cat.question_set.count(),
                initial=(preset or {}).get(cat.code, 0),
                widget=forms.Select(
                    choices=[(i, i) for i in range(cat.question_set.count() + 1)],
                    attrs={"class": "form-select mb-2"},
                ),
            )
        # reorder fields: student, pass_percentage, must_include, then weight_*
        from collections import OrderedDict

        ordered_fields = OrderedDict()
        # static order first
        for name in ["student", "pass_percentage", "description", "must_include"]:
            ordered_fields[name] = self.fields.pop(name)
        # then all weight_ fields in sorted order
        weight_keys = sorted(k for k in self.fields if k.startswith("weight_"))
        for key in weight_keys:
            ordered_fields[key] = self.fields.pop(key)
        # reassign to self.fields
        self.fields = ordered_fields
