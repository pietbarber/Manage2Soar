from django import forms

from members.models import Member

from .models import DutyAssignment, DutyPreference, MemberBlackout


class MemberBlackoutForm(forms.ModelForm):
    class Meta:
        model = MemberBlackout
        fields = ["date", "note"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "note": forms.TextInput(
                attrs={
                    "placeholder": "(Optional) Reason for blackout",
                    "class": "form-control",
                }
            ),
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
    max_assignments_per_month = forms.ChoiceField(
        choices=[(i, str(i)) for i in range(0, 13)],  # 0–12
        label="Max assignments per month",
        initial=lambda: DutyPreference._meta.get_field(
            "max_assignments_per_month"
        ).default,
    )

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
            "allow_weekend_double",
        ]
        widgets = {
            "suspended_reason": forms.TextInput(attrs={"placeholder": "Optional"}),
        }

    def __init__(self, *args, member=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.member = member

        # Make percentage fields not required if user doesn't have those roles
        # and set appropriate defaults
        if member:
            # Count how many roles the member has
            role_count = sum(
                [
                    member.instructor,
                    member.duty_officer,
                    member.assistant_duty_officer,
                    member.towpilot,
                ]
            )

            # If member has only one role, default it to 100%
            if not member.instructor:
                self.fields["instructor_percent"].required = False
                self.fields["instructor_percent"].initial = 0
            elif role_count == 1:
                # Only an instructor, set to 100% and make not required since we'll auto-set it
                self.fields["instructor_percent"].required = False
                self.fields["instructor_percent"].initial = 100

            if not member.duty_officer:
                self.fields["duty_officer_percent"].required = False
                self.fields["duty_officer_percent"].initial = 0
            elif role_count == 1:
                # Only a duty officer, set to 100% and make not required
                self.fields["duty_officer_percent"].required = False
                self.fields["duty_officer_percent"].initial = 100

            if not member.assistant_duty_officer:
                self.fields["ado_percent"].required = False
                self.fields["ado_percent"].initial = 0
            elif role_count == 1:
                # Only an ADO, set to 100% and make not required
                self.fields["ado_percent"].required = False
                self.fields["ado_percent"].initial = 100

            if not member.towpilot:
                self.fields["towpilot_percent"].required = False
                self.fields["towpilot_percent"].initial = 0
            elif role_count == 1:
                # Only a towpilot, set to 100% and make not required
                self.fields["towpilot_percent"].required = False
                self.fields["towpilot_percent"].initial = 100

    def clean(self):
        cleaned_data = super().clean()

        # Set default values for roles the member doesn't have
        # and handle single-role members automatically
        if self.member:
            role_count = sum(
                [
                    self.member.instructor,
                    self.member.duty_officer,
                    self.member.assistant_duty_officer,
                    self.member.towpilot,
                ]
            )

            # Set defaults for roles they don't have
            if not self.member.instructor:
                cleaned_data["instructor_percent"] = 0
            if not self.member.duty_officer:
                cleaned_data["duty_officer_percent"] = 0
            if not self.member.assistant_duty_officer:
                cleaned_data["ado_percent"] = 0
            if not self.member.towpilot:
                cleaned_data["towpilot_percent"] = 0

            # If member has only one role, automatically set it to 100%
            if role_count == 1:
                if self.member.instructor:
                    cleaned_data["instructor_percent"] = 100
                elif self.member.duty_officer:
                    cleaned_data["duty_officer_percent"] = 100
                elif self.member.assistant_duty_officer:
                    cleaned_data["ado_percent"] = 100
                elif self.member.towpilot:
                    cleaned_data["towpilot_percent"] = 100

        total = (
            cleaned_data.get("instructor_percent", 0)
            + cleaned_data.get("duty_officer_percent", 0)
            + cleaned_data.get("ado_percent", 0)
            + cleaned_data.get("towpilot_percent", 0)
        )
        if total not in (0, 100):
            raise forms.ValidationError(
                "Your total duty percentages must add up to 100% or be all 0."
            )
        return cleaned_data


# duty_roster/forms.py


class DutyAssignmentForm(forms.ModelForm):
    class Meta:
        model = DutyAssignment
        fields = [
            "instructor",
            "surge_instructor",
            "tow_pilot",
            "surge_tow_pilot",
            "duty_officer",
            "assistant_duty_officer",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Optional: Limit dropdowns to members with the right roles
        from members.utils.membership import get_active_membership_statuses

        active_statuses = get_active_membership_statuses()
        active_members = Member.objects.filter(membership_status__in=active_statuses)
        self.fields["instructor"].queryset = active_members.filter(
            instructor=True
        ).order_by("last_name", "first_name")
        self.fields["surge_instructor"].queryset = active_members.filter(
            instructor=True
        ).order_by("last_name", "first_name")
        self.fields["tow_pilot"].queryset = active_members.filter(
            towpilot=True
        ).order_by("last_name", "first_name")
        self.fields["surge_tow_pilot"].queryset = active_members.filter(
            towpilot=True
        ).order_by("last_name", "first_name")
        self.fields["duty_officer"].queryset = active_members.filter(
            duty_officer=True
        ).order_by("last_name", "first_name")
        self.fields["assistant_duty_officer"].queryset = active_members.filter(
            assistant_duty_officer=True
        ).order_by("last_name", "first_name")
