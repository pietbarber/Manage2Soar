from datetime import date, timedelta

# TestBuilderForm: Form for creating written test templates
from django import forms
from django.forms import formset_factory
from tinymce.widgets import TinyMCE

from members.models import Member

from .models import (
    SCORE_CHOICES,
    ClubQualificationType,
    GroundInstruction,
    InstructionReport,
    MemberQualification,
    SyllabusDocument,
    TrainingLesson,
)


class TestBuilderForm(forms.Form):
    pass_percentage = forms.DecimalField(
        max_digits=5,
        decimal_places=2,
        initial=100,
        help_text="Minimum % score required to pass",
    )

    student = forms.ModelChoiceField(
        queryset=Member.objects.filter(is_active=True),
        help_text="Who should take this test",
        widget=forms.Select(attrs={"class": "form-select"}),
    )


####################################################
# InstructionReportForm
#
# A ModelForm for creating and editing an InstructionReport.
# Fields:
# - report_text: HTML summary of the session (TinyMCE widget).
# - simulator: Boolean flag for simulator sessions.
####################################################


class InstructionReportForm(forms.ModelForm):
    class Meta:
        model = InstructionReport
        fields = ["report_text", "simulator"]
        widgets = {
            "report_text": TinyMCE(
                attrs={"cols": 80, "rows": 10, "class": "form-control"}
            ),
            "simulator": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


####################################################
# LessonScoreSimpleForm
#
# A simple Form to capture a single lesson score entry.
# Fields:
# - lesson: Hidden ModelChoiceField for TrainingLesson.
# - score: Select field for SCORE_CHOICES with optional blank.
####################################################


class LessonScoreSimpleForm(forms.Form):
    lesson = forms.ModelChoiceField(
        queryset=TrainingLesson.objects.all(), widget=forms.HiddenInput()
    )
    score = forms.ChoiceField(
        choices=[("", "---------")] + SCORE_CHOICES,
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )


####################################################
# LessonScoreSimpleFormSet
#
# A FormSet factory for LessonScoreSimpleForm with no extra forms.
####################################################


LessonScoreSimpleFormSet = formset_factory(LessonScoreSimpleForm, extra=0)


####################################################
# GroundInstructionForm
#
# A ModelForm for logging a ground instruction session.
# Fields:
# - date: Date of session (HTML date input).
# - location: Optional location text.
# - duration: Text input parsed into timedelta.
# - notes: HTMLField for detailed notes (TinyMCE widget).
####################################################


class GroundInstructionForm(forms.ModelForm):
    class Meta:
        model = GroundInstruction
        fields = ["date", "location", "duration", "notes"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "location": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Location of instruction",
                }
            ),
            "duration": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "HH:MM or HH:MM:SS"}
            ),
            "notes": TinyMCE(attrs={"rows": 6, "class": "form-control"}),
        }

    def clean_duration(self):
        val = self.cleaned_data.get("duration")

        if isinstance(val, str):
            try:
                parts = val.split(":")
                if len(parts) == 2:
                    hours, minutes = map(int, parts)
                    seconds = 0
                elif len(parts) == 3:
                    hours, minutes, seconds = map(int, parts)
                else:
                    raise ValueError
                return timedelta(hours=hours, minutes=minutes, seconds=seconds)
            except ValueError:
                raise forms.ValidationError(
                    "Enter duration in HH:MM or HH:MM:SS format."
                )
        elif isinstance(val, timedelta):
            return val
        elif not val:
            return None

        raise forms.ValidationError("Invalid format for duration.")


####################################################
# GroundLessonScoreSimpleForm
#
# A simple Form to capture a ground lesson score.
# Fields:
# - lesson: Hidden integer field for lesson ID.
# - score: Select field for SCORE_CHOICES with optional blank.
####################################################


class GroundLessonScoreSimpleForm(forms.Form):
    lesson = forms.IntegerField(widget=forms.HiddenInput())
    score = forms.ChoiceField(
        choices=[("", "---------")] + SCORE_CHOICES,
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )


####################################################
# SyllabusDocumentForm
#
# A ModelForm for editing SyllabusDocument entries.
# Fields:
# - title: Document title.
# - content: HTML content (TinyMCE widget).
####################################################


class SyllabusDocumentForm(forms.ModelForm):
    class Meta:
        model = SyllabusDocument
        fields = ["title", "content"]


####################################################
# GroundLessonScoreFormSet
#
# A FormSet factory for GroundLessonScoreSimpleForm with no extra forms.
####################################################


GroundLessonScoreFormSet = formset_factory(
    GroundLessonScoreSimpleForm,
    extra=0,
    can_delete=False,
    validate_min=False,
    validate_max=False,
)

####################################################
# QualificationAssignForm
#
# A ModelForm for assigning or updating a MemberQualification.
# Custom init to store instructor and student context.
# Overrides save() to update_or_create qualification record.
####################################################


class QualificationAssignForm(forms.ModelForm):
    class Meta:
        model = MemberQualification
        fields = [
            "qualification",
            "is_qualified",
            "expiration_date",
            "date_awarded",
            "notes",
        ]
        widgets = {
            "expiration_date": forms.DateInput(attrs={"type": "date"}),
            "date_awarded": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, instructor=None, student=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.instructor = instructor
        self.student = student
        self.fields["date_awarded"].label = "Date Awarded (optional)"
        self.fields["expiration_date"].label = "Expiration Date (optional)"

        # Filter out obsolete qualifications from the dropdown
        self.fields["qualification"].queryset = ClubQualificationType.objects.filter(
            is_obsolete=False
        ).order_by("name")

    from datetime import date  # at the top of forms.py

    def save(self, commit=True):
        date_awarded = self.cleaned_data.get("date_awarded") or date.today()

        instance, _ = MemberQualification.objects.update_or_create(
            member=self.student,
            qualification=self.cleaned_data["qualification"],
            defaults={
                "is_qualified": self.cleaned_data["is_qualified"],
                "expiration_date": self.cleaned_data["expiration_date"],
                "date_awarded": date_awarded,
                "notes": self.cleaned_data["notes"],
                "instructor": self.instructor,
                "imported": False,
            },
        )
        return instance


####################################################
# BulkQualificationAssignForm
#
# A form for assigning a single qualification to multiple members at once.
# Used by the safety officer to record attendance for mandatory meetings
# (e.g., annual safety meeting) without clicking through each member
# individually.
#
# Fields:
# - qualification: Qualification type to assign.
# - date_awarded: Date the qualification was earned (defaults to today).
# - expiration_date: Optional expiration date.
# - notes: Optional notes for all awarded records.
# - members: Multiple-choice checkbox list of active members.
#
# Methods:
# - save(instructor): Creates MemberQualification records for each
#   selected member, using bulk_create for new records and bulk_update
#   for existing ones to efficiently handle duplicates in batches.
####################################################


class BulkQualificationAssignForm(forms.Form):
    qualification = forms.ModelChoiceField(
        queryset=ClubQualificationType.objects.filter(is_obsolete=False).order_by(
            "name"
        ),
        label="Qualification",
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    date_awarded = forms.DateField(
        initial=date.today,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
        label="Date Awarded",
    )

    expiration_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
        label="Expiration Date (optional)",
    )

    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 2, "class": "form-control"}),
        label="Notes (optional)",
    )

    members = forms.ModelMultipleChoiceField(
        queryset=Member.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        label="Members",
        error_messages={"required": "Please select at least one member."},
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from members.utils.membership import get_active_membership_statuses

        active_statuses = get_active_membership_statuses()
        self.fields["members"].queryset = Member.objects.filter(
            membership_status__in=active_statuses
        ).order_by("last_name", "first_name")

    def save(self, instructor):
        """Create MemberQualification records for all selected members.

        Uses bulk operations to efficiently handle large numbers of members.
        For existing qualifications, updates them in bulk; for new ones,
        creates them in bulk. Wrapped in atomic transaction to prevent
        race conditions with concurrent requests.

        Uses Django 5.x's bulk_create with update_conflicts to handle
        concurrent insertions gracefully (upsert behavior).

        Returns:
            tuple: (created_count, updated_count)
        """
        from django.db import transaction

        qualification = self.cleaned_data["qualification"]
        date_awarded = self.cleaned_data["date_awarded"]
        expiration_date = self.cleaned_data.get("expiration_date")
        notes = self.cleaned_data.get("notes", "")
        members = self.cleaned_data["members"]

        with transaction.atomic():
            # Find which members already have this qualification
            existing_mqs = MemberQualification.objects.filter(
                member__in=members,
                qualification=qualification,
            ).select_related("member")

            existing_member_ids = {mq.member_id for mq in existing_mqs}

            # Update existing qualifications in bulk
            to_update = []
            for mq in existing_mqs:
                mq.is_qualified = True
                mq.date_awarded = date_awarded
                mq.expiration_date = expiration_date
                mq.notes = notes
                mq.instructor = instructor
                mq.imported = False
                to_update.append(mq)

            if to_update:
                MemberQualification.objects.bulk_update(
                    to_update,
                    fields=[
                        "is_qualified",
                        "date_awarded",
                        "expiration_date",
                        "notes",
                        "instructor",
                        "imported",
                    ],
                )

            # Create new qualifications in bulk with upsert behavior
            # to handle concurrent inserts (e.g., double-submit, parallel requests)
            to_create = []
            for member in members:
                if member.id not in existing_member_ids:
                    to_create.append(
                        MemberQualification(
                            member=member,
                            qualification=qualification,
                            is_qualified=True,
                            date_awarded=date_awarded,
                            expiration_date=expiration_date,
                            notes=notes,
                            instructor=instructor,
                            imported=False,
                        )
                    )

            if to_create:
                # Use Django 5.x update_conflicts to handle race conditions
                # If a concurrent transaction inserts the same (member, qualification),
                # update it instead of raising IntegrityError
                MemberQualification.objects.bulk_create(
                    to_create,
                    update_conflicts=True,
                    unique_fields=["member", "qualification"],
                    update_fields=[
                        "is_qualified",
                        "date_awarded",
                        "expiration_date",
                        "notes",
                        "instructor",
                        "imported",
                    ],
                )

        return len(to_create), len(to_update)
