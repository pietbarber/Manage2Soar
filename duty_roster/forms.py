from django import forms
from members.models import Member
from .models import MemberBlackout, DutyPreference, DutyAssignment

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
    class Meta:
        model = DutyPreference
        fields = [
            "dont_schedule",
            "scheduling_suspended",
            "suspended_reason",
            "preferred_day",
            "comment",
            "instructor_percent",
            "duty_officer_percent",
            "ado_percent",
            "towpilot_percent",
            "max_assignments_per_month",
        ]
        widgets = {
            "suspended_reason": forms.TextInput(attrs={"placeholder": "Optional"}),
        }

    def clean(self):
        cleaned_data = super().clean()
        total = (
            cleaned_data.get("instructor_percent", 0)
            + cleaned_data.get("duty_officer_percent", 0)
            + cleaned_data.get("ado_percent", 0)
            + cleaned_data.get("towpilot_percent", 0)
        )
        if total not in (0, 100):
            raise forms.ValidationError("Your total duty percentages must add up to 100% or be all 0.")
        return cleaned_data

# duty_roster/forms.py


class DutyAssignmentForm(forms.ModelForm):
    class Meta:
        model = DutyAssignment
        fields = [
            "instructor", "surge_instructor",
            "tow_pilot", "surge_tow_pilot",
            "duty_officer", "assistant_duty_officer",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Optional: Limit dropdowns to members with the right roles
        from members.constants.membership import DEFAULT_ACTIVE_STATUSES
        active_members = Member.objects.filter(membership_status__in=DEFAULT_ACTIVE_STATUSES)
        self.fields["instructor"].queryset = active_members.filter(instructor=True).order_by("last_name", "first_name")
        self.fields["surge_instructor"].queryset = active_members.filter(instructor=True).order_by("last_name", "first_name")
        self.fields["tow_pilot"].queryset = active_members.filter(towpilot=True).order_by("last_name", "first_name")
        self.fields["surge_tow_pilot"].queryset = active_members.filter(towpilot=True).order_by("last_name", "first_name")
        self.fields["duty_officer"].queryset = active_members.filter(duty_officer=True).order_by("last_name", "first_name")
        self.fields["assistant_duty_officer"].queryset = active_members.filter(assistant_duty_officer=True).order_by("last_name", "first_name")
