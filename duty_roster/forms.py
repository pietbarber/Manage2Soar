from django import forms
from members.models import Member
from .models import MemberBlackout, DutyPreference


class MemberBlackoutForm(forms.ModelForm):
    class Meta:
        model = MemberBlackout
        fields = ["date", "note"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "note": forms.TextInput(attrs={"placeholder": "(Optional) Reason for blackout", "class": "form-control"}),
        }

    def __init__(self, *args, member=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.member = member

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.member = self.member
        if commit:
            instance.save()
        return instance

class DutyPreferenceForm(forms.ModelForm):
    pair_with = forms.ModelMultipleChoiceField(
        queryset=Member.objects.filter(is_active=True),
        required=False,
        widget=forms.SelectMultiple(attrs={"class": "form-select"})
    )

    avoid_with = forms.ModelMultipleChoiceField(
        queryset=Member.objects.filter(is_active=True),
        required=False,
        widget=forms.SelectMultiple(attrs={"class": "form-select"})
    )

    class Meta:
        model = DutyPreference
        fields = [
            "preferred_day",
            "dont_schedule",
            "scheduling_suspended",
            "suspended_reason",
            "instructor_percent",
            "duty_officer_percent",
            "ado_percent",
            "towpilot_percent",
        ]
