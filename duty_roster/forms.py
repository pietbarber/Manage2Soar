from django import forms

from members.models import Member

from .models import DutyAssignment, DutyPreference, MemberBlackout

# Maps member role attributes to their corresponding form field names
DUTY_ROLE_FIELDS = [
    ("instructor", "instructor_percent"),
    ("duty_officer", "duty_officer_percent"),
    ("assistant_duty_officer", "ado_percent"),
    ("towpilot", "towpilot_percent"),
]


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

    def _count_member_roles(self, member):
        """Count how many duty roles the member has."""
        if not member:
            return 0
        return sum(
            getattr(member, role_attr, False) for role_attr, _ in DUTY_ROLE_FIELDS
        )

    def _get_single_role_field(self, member):
        """Get the percentage field name for a member's single role, or None if multiple/no roles."""
        if not member or self._count_member_roles(member) != 1:
            return None

        for role_attr, field_name in DUTY_ROLE_FIELDS:
            if getattr(member, role_attr, False):
                return field_name

        return None

    def __init__(self, *args, member=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.member = member

        # Make percentage fields not required if user doesn't have those roles
        # and set appropriate defaults
        if member:
            # Count how many roles the member has
            role_count = self._count_member_roles(member)

            # If member has only one role, default it to 100%
            for role_attr, field_name in DUTY_ROLE_FIELDS:
                has_role = getattr(member, role_attr, False)
                if not has_role:
                    self.fields[field_name].required = False
                    self.fields[field_name].initial = 0
                elif role_count == 1:
                    # Only this role, set to 100% and make not required since we'll auto-set it
                    self.fields[field_name].required = False
                    self.fields[field_name].initial = 100

    def clean(self):
        cleaned_data = super().clean()

        # Handle single-role members automatically
        single_role_field = (
            self._get_single_role_field(self.member) if self.member else None
        )
        if self.member and single_role_field:
            cleaned_data[single_role_field] = 100

        # Validate that dont_schedule requires a reason
        suspended_reason = cleaned_data.get("suspended_reason") or ""
        if cleaned_data.get("dont_schedule") and not suspended_reason.strip():
            raise forms.ValidationError(
                {
                    "suspended_reason": "A reason is required when requesting not to be scheduled."
                }
            )

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
