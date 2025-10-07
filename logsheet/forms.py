from .models import Logsheet, Airfield
from typing import Optional
from django.core.exceptions import ValidationError
from django import forms
from .models import Logsheet, Flight, Towplane, LogsheetCloseout, TowplaneCloseout
from members.models import Member
from django.utils.timezone import localtime, now
from django.forms import modelformset_factory
from tinymce.widgets import TinyMCE
from members.constants.membership import DEFAULT_ACTIVE_STATUSES
from django.db.models import Case, When, Value, IntegerField
from logsheet.models import MaintenanceIssue, Glider, Towplane


def get_active_members_with_role(role_flag: Optional[str] = None):
    qs = Member.objects.filter(membership_status__in=DEFAULT_ACTIVE_STATUSES)
    if role_flag:
        qs = qs.filter(**{role_flag: True})
    return qs.order_by("last_name", "first_name")


def get_active_members():
    return Member.objects.filter(
        membership_status__in=DEFAULT_ACTIVE_STATUSES
    ).order_by("last_name", "first_name")


# FlightForm
# This form is used to handle the creation and editing of Flight model instances.
# It includes fields for launch and landing times, pilot, instructor, glider, towplane, tow pilot, release altitude, passenger, and cost-splitting details.
# Widgets are customized for better user experience:
# - TimeInput widgets for "launch_time" and "landing_time" with "time" input type and "form-control" class.
# - Select widgets for dropdown fields like "pilot", "instructor", "glider", "tow_pilot", "towplane", "release_altitude", "passenger", and "split_type" with "form-select" class.
# - TextInput widgets for "passenger_name" with a placeholder and "form-control" class.
# The __init__ method customizes querysets for specific fields:
# - Filters active towplanes for "towplane".
# - Filters members who are instructors for "instructor".
# - Filters members who are tow pilots for "tow_pilot".
# - Filters active members for "split_with", ordered by last name.
# Additionally, if the form is for a new instance, the "launch_time" field is pre-filled with the current local time.
class FlightForm(forms.ModelForm):
    def clean(self):
        cleaned_data = super().clean()
        glider = cleaned_data.get("glider")
        launch_time = cleaned_data.get("launch_time")
        landing_time = cleaned_data.get("landing_time")
        logsheet = cleaned_data.get("logsheet") if "logsheet" in cleaned_data else getattr(
            self.instance, "logsheet", None)

        # Prevent landing time earlier than launch time
        if launch_time and landing_time:
            if landing_time < launch_time:
                raise forms.ValidationError(
                    "Landing time cannot be earlier than launch time.")

        # Only check if a glider and launch_time are provided
        if glider and launch_time:
            # Defensive: ensure logsheet and log_date are present
            if not logsheet or not hasattr(logsheet, 'log_date') or logsheet.log_date is None:
                # If missing, skip overlap check (or optionally raise a ValidationError)
                return cleaned_data
            from django.db.models import Q
            flights_qs = Flight.objects.filter(
                glider=glider, logsheet__log_date=logsheet.log_date)
            if self.instance.pk:
                flights_qs = flights_qs.exclude(pk=self.instance.pk)

            # Overlap logic: (A starts before B ends) and (A ends after B starts)
            for other in flights_qs:
                other_launch = other.launch_time
                other_landing = other.landing_time
                # If either flight has no landing time, treat as 'still airborne'
                if not other_launch:
                    continue
                # If both have landing times, check for overlap
                if landing_time and other_landing:
                    if (launch_time < other_landing and landing_time > other_launch):
                        raise forms.ValidationError(
                            f"This glider is already scheduled for another flight (ID {other.pk}) from {other_launch} to {other_landing}.")
                # If this flight has no landing, check if launch is during another flight
                elif not landing_time and other_landing:
                    if launch_time < other_landing and launch_time >= other_launch:
                        raise forms.ValidationError(
                            f"This glider is already airborne in another flight (ID {other.pk}) from {other_launch} to {other_landing}.")
                # If other flight has no landing, check for overlap
                elif landing_time and not other_landing:
                    if landing_time > other_launch and launch_time <= other_launch:
                        raise forms.ValidationError(
                            f"This glider is already airborne in another flight (ID {other.pk}) starting at {other_launch}.")
                # If neither has landing time, both are open-ended
                elif not landing_time and not other_landing:
                    if launch_time == other_launch:
                        raise forms.ValidationError(
                            f"This glider is already airborne in another open-ended flight (ID {other.pk}) at {other_launch}.")

        return cleaned_data

    class Meta:
        model = Flight
        fields = [
            "launch_time",
            "landing_time",
            "pilot",
            "instructor",
            "glider",
            "towplane",
            "tow_pilot",
            "release_altitude",
            "passenger",
            "passenger_name",
            "split_with",
            "split_type"
        ]
        widgets = {
            "launch_time": forms.TimeInput(attrs={"type": "time", "class": "form-control timeinput"}),
            "landing_time": forms.TimeInput(attrs={"type": "time", "class": "form-control timeinput"}),
            "pilot": forms.Select(attrs={"class": "form-select"}),
            "instructor": forms.Select(attrs={"class": "form-select"}),
            "glider": forms.Select(attrs={"class": "form-select"}),
            "tow_pilot": forms.Select(attrs={"class": "form-select"}),
            "towplane": forms.Select(attrs={"class": "form-select"}),
            "release_altitude": forms.Select(attrs={"class": "form-select"}),
            "launch_time": forms.TextInput(attrs={"type": "text", "class": "form-control"}),
            "landing_time": forms.TextInput(attrs={"type": "text", "class": "form-control"}),
            "passenger": forms.Select(attrs={"class": "form-select"}),
            "passenger_name": forms.TextInput(attrs={"placeholder": "If not a member", "class": "form-control"}),
            "split_type": forms.Select(attrs={"class": "form-select"}),

        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Ensure launch_time and landing_time are always formatted as HH:MM (no seconds)
        for field_name in ["launch_time", "landing_time"]:
            value = self.initial.get(field_name) or getattr(
                self.instance, field_name, None)
            if value:
                # value may be a datetime.time or string
                if hasattr(value, 'strftime'):
                    self.initial[field_name] = value.strftime('%H:%M')
                elif isinstance(value, str) and len(value) >= 5:
                    self.initial[field_name] = value[:5]

        # Filter instructors only
        self.fields["pilot"].queryset = get_active_members().order_by(
            "first_name", "last_name")
        self.fields["instructor"].queryset = get_active_members_with_role(
            "instructor")
        # Ensure the logsheet's scheduled tow pilot is included and selected by default
        # Sort passenger dropdown by last name, first name
        if "passenger" in self.fields:
            self.fields["passenger"].queryset = self.fields["passenger"].queryset.order_by(
                "first_name", "last_name")
        tow_pilot_initial = self.initial.get("tow_pilot")
        tow_pilot_qs = get_active_members_with_role("towpilot")
        if tow_pilot_initial:
            # Make sure the scheduled tow pilot is in the queryset
            tow_pilot_qs = tow_pilot_qs | Member.objects.filter(
                pk=tow_pilot_initial)
            # Move the scheduled tow pilot to the top for better UX
            tow_pilot_qs = tow_pilot_qs.distinct().order_by(
                Case(
                    When(pk=tow_pilot_initial, then=0),
                    default=1,
                    output_field=IntegerField()
                ),
                "first_name", "last_name"
            )
        self.fields["tow_pilot"].queryset = tow_pilot_qs
        self.fields["split_with"].queryset = get_active_members().order_by(
            "first_name", "last_name")

        # Custom towplane sort: club-owned active first, then others, with optgroup labels
        towplanes = [tp for tp in Towplane.objects.all(
        ) if tp.is_active and not tp.is_grounded]
        club_towplanes = sorted(
            [tp for tp in towplanes if tp.club_owned], key=lambda t: t.name)
        other_towplanes = sorted(
            [tp for tp in towplanes if not tp.club_owned], key=lambda t: t.name)

        # Build grouped choices for the select widget
        towplane_choices = []
        if club_towplanes:
            towplane_choices.append(
                ("Club towplanes", [(tp.pk, str(tp)) for tp in club_towplanes]))
        if other_towplanes:
            towplane_choices.append(
                ("Other", [(tp.pk, str(tp)) for tp in other_towplanes]))

        self.fields["towplane"].choices = towplane_choices
        # Optionally, add a visual divider for winch/self-launch if needed
        # (Assumes these are represented as special Towplane objects or handled elsewhere)

        # Custom glider sort: club two-seaters, club one-seaters, private active, inactive
        gliders = Glider.objects.all()

        def glider_sort_key(g):
            # 0 for club-owned, active, two-seater; 1 for all others
            return 0 if g.club_owned and g.is_active and g.seats == 2 else 1

        gliders_sorted = sorted(
            [g for g in gliders if not g.is_grounded],
            key=glider_sort_key
        )
        self.fields["glider"].choices = [
            (g.pk, str(g)) for g in gliders_sorted
        ]

        COMMON_ALTITUDES = [3000, 1500, 2000, 2500, 4000]
        ALL_ALTITUDES = list(range(0, 7100, 100))

        # Remove common ones from the base list to avoid duplicates
        remaining = [
            alt for alt in ALL_ALTITUDES if alt not in COMMON_ALTITUDES]

        self.fields["release_altitude"].choices = (
            [(alt, f"{alt} ft") for alt in COMMON_ALTITUDES] +
            [('', '──────────')] +  # Optional visual divider
            [(alt, f"{alt} ft") for alt in remaining]
        )

        glider_obj = None
        if "glider" in self.initial or "glider" in self.data:
            glider_id = self.initial.get("glider") or self.data.get("glider")
            try:
                glider_obj = Glider.objects.get(pk=glider_id)
                owner_ids = glider_obj.owners.values_list("pk", flat=True)
            except Glider.DoesNotExist:
                owner_ids = []

            self.fields["pilot"].queryset = Member.objects.filter(
                membership_status__in=DEFAULT_ACTIVE_STATUSES
            ).annotate(
                owner_rank=Case(
                    When(pk__in=owner_ids, then=Value(0)),
                    default=Value(1),
                    output_field=IntegerField()
                )
            ).order_by("owner_rank", "first_name", "last_name")

        else:
            self.fields["pilot"].queryset = get_active_members().order_by(
                "first_name", "last_name")

        if not self.initial.get("pilot") and not self.data.get("pilot"):
            if glider_obj and glider_obj.owners.count() == 1:
                owner = glider_obj.owners.first()
                if owner is not None:
                    self.initial["pilot"] = owner.pk


# CreateLogsheetForm
# This form is used to handle the creation of Logsheet model instances. It includes fields for log date, airfield, duty crew roles, and the default towplane. The form ensures that only one logsheet exists for a specific date and airfield combination.

# Widgets:
# - "log_date": DateInput widget with "date" input type and "form-control" class for selecting the log date.
# - "airfield": Select widget with "form-select" class, pre-filtered to show only active airfields, ordered by name.
# - Dropdown fields for duty crew roles ("duty_officer", "assistant_duty_officer", "duty_instructor", "surge_instructor", "tow_pilot", "surge_tow_pilot") and "default_towplane" are styled with the "form-select" class.

# Methods:
#    - `clean`: Validates that a logsheet does not already exist for the selected date and airfield. Raises a ValidationError if a duplicate is found.
#    - `__init__`:
#        - Initializes the form with filtered querysets for dropdown fields:
#        - Filters active airfields for "airfield".
#        - Filters members based on their roles for duty crew fields (e.g., duty officer, instructor, tow pilot).
#        - Orders members by last name for better usability.
#        - Orders towplanes by name and n_number.
#        - Sets the default airfield to "KFRR" if it exists.
#        - Applies consistent widget styles for dropdown fields.
class CreateLogsheetForm(forms.ModelForm):
    class Meta:
        model = Logsheet
        fields = [
            "log_date", "airfield",
            "duty_officer", "assistant_duty_officer",
            "duty_instructor", "surge_instructor",
            "tow_pilot", "surge_tow_pilot",
            "default_towplane",
        ]
        widgets = {
            "log_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
        }

    def clean(self):
        cleaned_data = super().clean()
        log_date = cleaned_data.get("log_date")
        airfield = cleaned_data.get("airfield")

        if log_date and airfield:
            if Logsheet.objects.filter(log_date=log_date, airfield=airfield).exists():
                raise ValidationError(
                    "A logsheet for this date and airfield already exists.")

        return cleaned_data

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["log_date"].widget.attrs.update({"class": "form-control"})
        self.fields["airfield"].queryset = Airfield.objects.filter(
            is_active=True).order_by("name")
        self.fields["airfield"].widget.attrs.update({"class": "form-select"})

        default_airfield = Airfield.objects.filter(identifier="KFRR").first()
        if default_airfield:
            self.fields["airfield"].initial = default_airfield

        # Setup filtered querysets for each duty crew role
        self.fields["duty_officer"].queryset = get_active_members_with_role(
            "duty_officer")
        self.fields["assistant_duty_officer"].queryset = get_active_members_with_role(
            "assistant_duty_officer")
        self.fields["duty_instructor"].queryset = get_active_members_with_role(
            "instructor")
        self.fields["surge_instructor"].queryset = get_active_members_with_role(
            "instructor")
        self.fields["tow_pilot"].queryset = get_active_members_with_role(
            "towpilot")
        self.fields["surge_tow_pilot"].queryset = get_active_members_with_role(
            "towpilot")
        self.fields["default_towplane"].queryset = Towplane.objects.filter(
            is_active=True).order_by("name", "n_number")

        # Optional: set widget styles for dropdowns
        for name in [
            "duty_officer", "assistant_duty_officer",
            "duty_instructor", "surge_instructor",
            "tow_pilot", "surge_tow_pilot",
            "default_towplane",
        ]:
            self.fields[name].required = False
            self.fields[name].widget.attrs.update({"class": "form-select"})

        # Set dynamic labels for duty crew fields using siteconfig
        try:
            from siteconfig.models import SiteConfiguration
            config = SiteConfiguration.objects.first()
        except Exception:
            config = None
        if config:
            self.fields["duty_officer"].label = config.duty_officer_title or "Duty Officer"
            self.fields["assistant_duty_officer"].label = config.assistant_duty_officer_title or "Assistant Duty Officer"
            self.fields["duty_instructor"].label = config.instructor_title or "Instructor"
            self.fields["surge_instructor"].label = config.surge_instructor_title or "Surge Instructor"
            self.fields["tow_pilot"].label = config.towpilot_title or "Tow Pilot"
            self.fields["surge_tow_pilot"].label = config.surge_towpilot_title or "Surge Tow Pilot"

######################################################
# LogsheetCloseoutForm
#
# Handles the editing of logsheet closeout reports.
# Allows the duty officer to enter safety issues, equipment issues,
# and a summary of operations for the day's flights.
#
# Fields:
# - safety_issues: Text field (TinyMCE rich text).
# - equipment_issues: Text field (TinyMCE rich text).
# - operations_summary: Text field (TinyMCE rich text).
#
# Widgets:
# - TinyMCE editor is used for all fields for better formatting.
#


class LogsheetCloseoutForm(forms.ModelForm):
    class Meta:
        model = LogsheetCloseout
        fields = ["safety_issues", "equipment_issues", "operations_summary"]
        widgets = {
            "safety_issues": TinyMCE(mce_attrs={"height": 200}),
            "equipment_issues": TinyMCE(mce_attrs={"height": 200}),
            "operations_summary": TinyMCE(mce_attrs={"height": 500}),

        }

######################################################
# LogsheetDutyCrewForm
#
# Allows updating the assigned duty crew for a given logsheet.
# Covers duty officer, assistant duty officer, duty instructors, and tow pilots.
#
# Fields:
# - duty_officer
# - assistant_duty_officer
# - duty_instructor
# - surge_instructor
# - tow_pilot
# - surge_tow_pilot
#
# Standard form with default select dropdowns.
#


class LogsheetDutyCrewForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Restrict all duty crew dropdowns to active members, alphabetized by last and first name
        self.fields["duty_officer"].queryset = get_active_members_with_role(
            "duty_officer")
        self.fields["assistant_duty_officer"].queryset = get_active_members_with_role(
            "assistant_duty_officer")
        self.fields["duty_instructor"].queryset = get_active_members_with_role(
            "instructor")
        self.fields["surge_instructor"].queryset = get_active_members_with_role(
            "instructor")
        self.fields["tow_pilot"].queryset = get_active_members_with_role(
            "towpilot")
        self.fields["surge_tow_pilot"].queryset = get_active_members_with_role(
            "towpilot")

        try:
            from siteconfig.models import SiteConfiguration
            config = SiteConfiguration.objects.first()
        except Exception:
            config = None
        if config:
            self.fields["duty_officer"].label = config.duty_officer_title or "Duty Officer"
            self.fields["assistant_duty_officer"].label = config.assistant_duty_officer_title or "Assistant Duty Officer"
            self.fields["duty_instructor"].label = config.instructor_title or "Instructor"
            self.fields["surge_instructor"].label = config.surge_instructor_title or "Surge Instructor"
            self.fields["tow_pilot"].label = config.towpilot_title or "Tow Pilot"
            self.fields["surge_tow_pilot"].label = config.surge_towpilot_title or "Surge Tow Pilot"

    class Meta:
        model = Logsheet
        fields = [
            "duty_officer",
            "assistant_duty_officer",
            "duty_instructor",
            "surge_instructor",
            "tow_pilot",
            "surge_tow_pilot",
        ]

######################################################
# TowplaneCloseoutFormSet
#
# A formset for entering end-of-day towplane closeout data.
# Allows editing multiple TowplaneCloseout entries at once, including
# tachometer readings, fuel added, and operational notes.
#
# Fields:
# - towplane
# - start_tach
# - end_tach
# - fuel_added
# - notes
#
# Widgets:
# - TinyMCE editor used for the 'notes' field.
#


# TowplaneCloseoutForm with optgroup logic for towplane field
class TowplaneCloseoutForm(forms.ModelForm):
    class Meta:
        model = TowplaneCloseout
        fields = ["towplane", "start_tach", "end_tach", "fuel_added", "notes"]
        widgets = {
            "notes": TinyMCE(mce_attrs={"height": 300}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        towplanes = [tp for tp in Towplane.objects.filter(
            is_active=True) if not tp.is_grounded]
        club_towplanes = sorted(
            [tp for tp in towplanes if tp.club_owned], key=lambda t: t.name)
        other_towplanes = sorted(
            [tp for tp in towplanes if not tp.club_owned], key=lambda t: t.name)
        towplane_choices = []
        if club_towplanes:
            towplane_choices.append(
                ("Club towplanes", [(tp.pk, str(tp)) for tp in club_towplanes]))
        if other_towplanes:
            towplane_choices.append(
                ("Other", [(tp.pk, str(tp)) for tp in other_towplanes]))
        self.fields["towplane"].choices = towplane_choices


TowplaneCloseoutFormSet = modelformset_factory(
    TowplaneCloseout,
    form=TowplaneCloseoutForm,
    extra=0,
)


class MaintenanceIssueForm(forms.ModelForm):
    class Meta:
        model = MaintenanceIssue
        fields = ["glider", "towplane", "description", "grounded"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4, "class": "form-control"}),
            "grounded": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "glider": forms.Select(attrs={"class": "form-select"}),
            "towplane": forms.Select(attrs={"class": "form-select"}),
        }

    def clean(self):
        cleaned_data = super().clean()
        glider = cleaned_data.get("glider")
        towplane = cleaned_data.get("towplane")

        if not glider and not towplane:
            raise forms.ValidationError(
                "You must select either a glider or a towplane.")

        return cleaned_data

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only show club-owned and active gliders
        self.fields["glider"].queryset = Glider.objects.filter(
            club_owned=True, is_active=True)

        # Custom towplane sort: club-owned first, then others, with optgroup labels (include inactive and grounded)
        towplanes = Towplane.objects.all()
        club_towplanes = sorted(
            [tp for tp in towplanes if tp.club_owned], key=lambda t: t.name)
        other_towplanes = sorted(
            [tp for tp in towplanes if not tp.club_owned], key=lambda t: t.name)

        towplane_choices = []
        if club_towplanes:
            towplane_choices.append(
                ("Club towplanes", [(tp.pk, str(tp)) for tp in club_towplanes]))
        if other_towplanes:
            towplane_choices.append(
                ("Other", [(tp.pk, str(tp)) for tp in other_towplanes]))
        self.fields["towplane"].choices = towplane_choices
