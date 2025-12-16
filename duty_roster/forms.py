import calendar

from django import forms
from django.db.models import Exists, OuterRef, Q

from logsheet.models import Glider, MaintenanceIssue
from members.models import Member
from siteconfig.models import SiteConfiguration

from .models import (
    DutyAssignment,
    DutyPreference,
    DutySwapOffer,
    DutySwapRequest,
    GliderReservation,
    InstructionSlot,
    MemberBlackout,
)

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


class InstructionRequestForm(forms.ModelForm):
    """Form for students to request instruction on a duty day."""

    class Meta:
        model = InstructionSlot
        fields = []  # No fields needed - assignment and student set in view

    def __init__(self, *args, assignment=None, student=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.assignment = assignment
        self.student = student

    def clean(self):
        cleaned_data = super().clean()

        if not self.assignment:
            raise forms.ValidationError("No duty assignment specified.")

        if not self.student:
            raise forms.ValidationError("No student specified.")

        # Check if student already has a request for this day
        existing = (
            InstructionSlot.objects.filter(
                assignment=self.assignment,
                student=self.student,
            )
            .exclude(status="cancelled")
            .exists()
        )

        if existing:
            raise forms.ValidationError(
                "You have already requested instruction for this day."
            )

        # Check if there's an instructor assigned
        if not self.assignment.instructor and not self.assignment.surge_instructor:
            raise forms.ValidationError(
                "No instructor is scheduled for this day. "
                "Please check back later or choose another day."
            )

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        assert self.assignment is not None  # Validated in clean()
        instance.assignment = self.assignment
        instance.student = self.student
        # Default to the primary instructor, or surge instructor if primary is None
        instance.instructor = (
            self.assignment.instructor or self.assignment.surge_instructor
        )
        instance.status = "pending"
        instance.instructor_response = "pending"
        if commit:
            instance.save()
        return instance


class InstructorResponseForm(forms.ModelForm):
    """Form for instructors to accept or reject student requests."""

    class Meta:
        model = InstructionSlot
        fields = ["instructor_note"]
        widgets = {
            "instructor_note": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Optional note to student (e.g., scheduling instructions, reasons for declining)",
                }
            ),
        }

    def __init__(self, *args, instructor=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.instructor = instructor

    def accept(self):
        """Accept the instruction request."""
        if self.instance and self.instructor:
            note = self.cleaned_data.get("instructor_note", "")
            self.instance.accept(instructor=self.instructor, note=note)
            return self.instance
        return None

    def reject(self):
        """Reject the instruction request."""
        if self.instance:
            note = self.cleaned_data.get("instructor_note", "")
            self.instance.reject(note=note)
            return self.instance
        return None


class DutySwapRequestForm(forms.ModelForm):
    """Form for creating a swap/coverage request."""

    class Meta:
        model = DutySwapRequest
        fields = ["request_type", "direct_request_to", "notes", "is_emergency"]
        widgets = {
            "request_type": forms.RadioSelect(
                attrs={"class": "form-check-input"},
            ),
            "notes": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Reason for needing coverage (e.g., 'Bar mitzvah', 'Out of town')",
                }
            ),
            "is_emergency": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
        labels = {
            "request_type": "Who should receive this request?",
            "direct_request_to": "Specific member",
            "notes": "Reason (optional but helpful)",
            "is_emergency": "This is urgent (less than 48 hours notice)",
        }

    def __init__(self, *args, role=None, date=None, requester=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.role = role
        self.date = date
        self.requester = requester

        # Ensure labels are set (sometimes Meta labels don't apply correctly)
        self.fields["request_type"].label = "Who should receive this request?"
        self.fields["request_type"].choices = [
            ("general", "Broadcast to all eligible members"),
            ("direct", "Request specific member"),
        ]
        self.fields["direct_request_to"].label = "Specific member"
        self.fields["notes"].label = "Reason (optional but helpful)"
        self.fields["is_emergency"].label = "This is urgent (less than 48 hours notice)"

        # Filter direct_request_to to only show eligible members for this role
        if role:
            role_attr_map = {
                "DO": "duty_officer",
                "ADO": "assistant_duty_officer",
                "INSTRUCTOR": "instructor",
                "TOW": "towpilot",
            }
            role_attr = role_attr_map.get(role)

            if role_attr:
                eligible = Member.objects.filter(
                    **{role_attr: True},
                    membership_status__in=["Full Member", "Family Member"],
                ).exclude(pk=requester.pk if requester else None)
                self.fields["direct_request_to"].queryset = eligible
            else:
                self.fields["direct_request_to"].queryset = Member.objects.none()

        self.fields["direct_request_to"].required = False
        self.fields["direct_request_to"].widget.attrs["class"] = "form-select"

    def clean(self):
        cleaned_data = super().clean()
        request_type = cleaned_data.get("request_type")
        direct_to = cleaned_data.get("direct_request_to")

        if request_type == "direct" and not direct_to:
            self.add_error(
                "direct_request_to",
                "Please select a specific member for a direct request.",
            )

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.role = self.role
        instance.original_date = self.date
        instance.requester = self.requester

        # If not direct, clear the direct_request_to field
        if instance.request_type != "direct":
            instance.direct_request_to = None

        if commit:
            instance.save()
        return instance


class DutySwapOfferForm(forms.ModelForm):
    """Form for making an offer to help with a swap request."""

    class Meta:
        model = DutySwapOffer
        fields = ["offer_type", "proposed_swap_date", "notes"]
        widgets = {
            "offer_type": forms.RadioSelect(attrs={"class": "form-check-input"}),
            "proposed_swap_date": forms.DateInput(
                attrs={"type": "date", "class": "form-control"}
            ),
            "notes": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 2,
                    "placeholder": "Optional note (e.g., 'I can only do morning shift')",
                }
            ),
        }
        labels = {
            "offer_type": "How would you like to help?",
            "proposed_swap_date": "If swapping, which date should they take?",
            "notes": "Note (optional)",
        }

    def __init__(self, *args, swap_request=None, offered_by=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.swap_request = swap_request
        self.offered_by = offered_by
        self.fields["proposed_swap_date"].required = False

        # Set choices on the field, not the widget
        # Make the swap option dynamic based on the request date
        swap_date_str = (
            swap_request.original_date.strftime("%b %d")
            if swap_request
            else "their date"
        )
        self.fields["offer_type"].choices = [
            ("cover", "Cover - I'll take this duty (no swap needed)"),
            ("swap", f"Swap - I'll take {swap_date_str} if they take my date"),
        ]

    def clean(self):
        from django.utils import timezone

        cleaned_data = super().clean()
        offer_type = cleaned_data.get("offer_type")
        proposed_date = cleaned_data.get("proposed_swap_date")

        if offer_type == "swap" and not proposed_date:
            self.add_error(
                "proposed_swap_date",
                "Please select a date for the swap.",
            )

        if proposed_date:
            today = timezone.now().date()
            if proposed_date < today:
                self.add_error(
                    "proposed_swap_date",
                    "Swap date must be in the future.",
                )

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.swap_request = self.swap_request
        instance.offered_by = self.offered_by

        # Clear proposed_swap_date if not a swap
        if instance.offer_type != "swap":
            instance.proposed_swap_date = None

        if commit:
            instance.save()
        return instance


class GliderReservationForm(forms.ModelForm):
    """Form for members to create glider reservations."""

    class Meta:
        model = GliderReservation
        fields = [
            "glider",
            "date",
            "reservation_type",
            "time_preference",
            "start_time",
            "end_time",
            "purpose",
        ]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "start_time": forms.TimeInput(
                attrs={"type": "time", "class": "form-control"}
            ),
            "end_time": forms.TimeInput(
                attrs={"type": "time", "class": "form-control"}
            ),
            "reservation_type": forms.Select(attrs={"class": "form-select"}),
            "time_preference": forms.Select(attrs={"class": "form-select"}),
            "glider": forms.Select(attrs={"class": "form-select"}),
            "purpose": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Optional: Additional details about your planned flight (badge attempt, guest info, etc.)",
                }
            ),
        }

    def __init__(self, *args, member=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.member = member

        # Filter gliders to only show club-owned, active, non-grounded gliders
        config = SiteConfiguration.objects.first()

        # Efficiently filter out grounded gliders using a database query
        # rather than loading all gliders and checking the is_grounded property
        grounded_subquery = MaintenanceIssue.objects.filter(
            glider=OuterRef("pk"), grounded=True, resolved=False
        )

        available_gliders = (
            Glider.objects.filter(
                is_active=True,
                club_owned=True,
            )
            .exclude(Exists(grounded_subquery))
            .order_by("competition_number")
        )

        # If two-seater reservations are not allowed, filter them out
        if config and not config.allow_two_seater_reservations:
            available_gliders = available_gliders.filter(seats=1)

        self.fields["glider"].queryset = available_gliders

        # Make start_time and end_time not required (they're only for specific time preference)
        self.fields["start_time"].required = False
        self.fields["end_time"].required = False
        self.fields["purpose"].required = False

        # Add helpful labels
        self.fields["reservation_type"].help_text = (
            "Select the type of flight you're planning."
        )
        self.fields["time_preference"].help_text = (
            "Choose when you'd like to fly. Select 'Specific Time' for exact times."
        )

    def clean(self):
        from django.db import transaction
        from django.utils import timezone

        cleaned_data = super().clean()
        time_preference = cleaned_data.get("time_preference")
        start_time = cleaned_data.get("start_time")
        end_time = cleaned_data.get("end_time")
        date = cleaned_data.get("date")

        # Validate time requirement for specific time preference
        if time_preference == "specific" and not start_time:
            self.add_error(
                "start_time",
                "Start time is required when using specific time preference.",
            )

        # Validate end_time is after start_time if both provided
        if start_time and end_time and end_time <= start_time:
            self.add_error(
                "end_time",
                "End time must be after start time.",
            )

        # Validate date is in the future (or today)
        if date:
            today = timezone.now().date()
            if date < today:
                self.add_error(
                    "date", "Reservation date must be today or in the future."
                )

        # Check for yearly reservation limits (use transaction to prevent race conditions)
        if self.member and date:
            with transaction.atomic():
                # Lock the member's reservations for this year to prevent concurrent modifications
                reservations_qs = GliderReservation.objects.filter(
                    member=self.member,
                    date__year=date.year,
                    status__in=["confirmed", "completed"],
                ).select_for_update()

                # Exclude the current instance if editing (not creating)
                if self.instance and self.instance.pk:
                    reservations_qs = reservations_qs.exclude(pk=self.instance.pk)

                # Get the reservation limit from SiteConfiguration or set a sensible default
                config = SiteConfiguration.objects.first()
                reservation_limit = getattr(config, "max_reservations_per_year", 3)
                current_count = reservations_qs.count()
                # Skip limit check if reservation_limit is 0 (unlimited)
                if reservation_limit > 0 and current_count >= reservation_limit:
                    self.add_error(
                        None,
                        f"You have reached the maximum of {reservation_limit} reservations for {date.year}.",
                    )

                # Check for monthly reservation limits
                monthly_limit = config.max_reservations_per_month
                if monthly_limit > 0:
                    monthly_reservations = GliderReservation.objects.filter(
                        member=self.member,
                        date__year=date.year,
                        date__month=date.month,
                        status__in=["confirmed", "completed"],
                    ).select_for_update()

                    # Exclude the current instance if editing
                    if self.instance and self.instance.pk:
                        monthly_reservations = monthly_reservations.exclude(
                            pk=self.instance.pk
                        )

                    monthly_count = monthly_reservations.count()
                    if monthly_count >= monthly_limit:
                        month_name = calendar.month_name[date.month]
                        self.add_error(
                            None,
                            f"You have reached the maximum of {monthly_limit} reservations for {month_name} {date.year}.",
                        )

        return cleaned_data

    def clean_glider(self):
        """Additional validation for the glider field."""
        glider = self.cleaned_data.get("glider")
        if not glider:
            return glider

        # Check two-seater reservation permission
        config = SiteConfiguration.objects.first()
        if glider.seats >= 2 and config and not config.allow_two_seater_reservations:
            raise forms.ValidationError(
                "Two-seater glider reservations are not currently allowed."
            )

        return glider

    def save(self, commit=True):
        from django.core.exceptions import ValidationError as DjangoValidationError
        from django.db import IntegrityError

        instance = super().save(commit=False)
        instance.member = self.member

        if commit:
            try:
                instance.full_clean()
                instance.save()
            except DjangoValidationError as e:
                # Re-add validation errors to the form for proper display
                if hasattr(e, "error_dict") and e.error_dict:
                    for field, errors in e.error_dict.items():
                        for error in errors:
                            if field == "__all__":
                                self.add_error(None, error)
                            else:
                                self.add_error(field, error)
                else:
                    self.add_error(None, str(e))
                # Don't save, return unsaved instance
                return instance
            except IntegrityError:
                # Handle race condition where another reservation was created
                self.add_error(
                    None,
                    "This glider is no longer available for the selected time. Please try again.",
                )
                return instance

        return instance


class GliderReservationCancelForm(forms.Form):
    """Form for cancelling a glider reservation."""

    cancellation_reason = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 2,
                "placeholder": "Optional: Reason for cancellation",
            }
        ),
        label="Reason for cancellation",
    )
