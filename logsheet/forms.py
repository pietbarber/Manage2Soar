from .models import Logsheet, Airfield
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


def get_active_members_with_role(role_flag: str = None):
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
            "launch_time": forms.TimeInput(attrs={"type": "time", "class": "form-control"}),
            "landing_time": forms.TimeInput(attrs={"type": "time", "class": "form-control"}),
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
        # Filter instructors only
        self.fields["pilot"].queryset = get_active_members()
        self.fields["instructor"].queryset = get_active_members_with_role("instructor")
        self.fields["tow_pilot"].queryset = get_active_members_with_role("towpilot")
        self.fields["split_with"].queryset = get_active_members()

        active_towplanes = Towplane.objects.filter(is_active=True)
        self.fields["towplane"].queryset = active_towplanes.exclude(
            id__in=[tp.id for tp in active_towplanes if tp.is_grounded]
        ).order_by("name", "registration")

        active_gliders = Glider.objects.filter(is_active=True)
        self.fields["glider"].queryset = active_gliders.exclude(
            id__in=[g.id for g in active_gliders if g.is_grounded]
        ).order_by("n_number")

        COMMON_ALTITUDES = [3000, 1500, 2000, 2500, 4000]
        ALL_ALTITUDES = list(range(0, 7100, 100))

        # Remove common ones from the base list to avoid duplicates
        remaining = [alt for alt in ALL_ALTITUDES if alt not in COMMON_ALTITUDES]

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
            ).order_by("owner_rank", "last_name", "first_name")

        else:
            self.fields["pilot"].queryset = get_active_members()

        if not self.initial.get("pilot") and not self.data.get("pilot"):
            if glider_obj and glider_obj.owners.count() == 1:
                self.initial["pilot"] = glider_obj.owners.first().pk


        if not self.instance.pk:
            self.fields["launch_time"].initial = localtime(now()).strftime("%H:%M")


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
#        - Orders towplanes by name and registration.
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
                raise ValidationError("A logsheet for this date and airfield already exists.")

        return cleaned_data

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["log_date"].widget.attrs.update({"class": "form-control"})
        self.fields["airfield"].queryset = Airfield.objects.filter(is_active=True).order_by("name")
        self.fields["airfield"].widget.attrs.update({"class": "form-select"})

        default_airfield = Airfield.objects.filter(identifier="KFRR").first()
        if default_airfield:
            self.fields["airfield"].initial = default_airfield

        # Setup filtered querysets for each duty crew role
        self.fields["duty_officer"].queryset = get_active_members_with_role("duty_officer")
        self.fields["assistant_duty_officer"].queryset = get_active_members_with_role("assistant_duty_officer")
        self.fields["duty_instructor"].queryset = get_active_members_with_role("instructor")
        self.fields["surge_instructor"].queryset = get_active_members_with_role("instructor")
        self.fields["tow_pilot"].queryset = get_active_members_with_role("towpilot")
        self.fields["surge_tow_pilot"].queryset = get_active_members_with_role("towpilot")
        self.fields["default_towplane"].queryset = Towplane.objects.filter(is_active=True).order_by("name", "registration") 

        # Optional: set widget styles for dropdowns
        for name in [
            "duty_officer", "assistant_duty_officer",
            "duty_instructor", "surge_instructor",
            "tow_pilot", "surge_tow_pilot",
            "default_towplane",
        ]:
            self.fields[name].required = False
            self.fields[name].widget.attrs.update({"class": "form-select"})

class LogsheetCloseoutForm(forms.ModelForm):
    class Meta:
        model = LogsheetCloseout
        fields = ["safety_issues", "equipment_issues", "operations_summary"]
        widgets = {
            "safety_issues": TinyMCE(mce_attrs={"height": 200}),
            "equipment_issues": TinyMCE(mce_attrs={"height": 200}),
            "operations_summary": TinyMCE(mce_attrs={"height": 500}),

        }


class LogsheetDutyCrewForm(forms.ModelForm):
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


TowplaneCloseoutFormSet = modelformset_factory(
    TowplaneCloseout,
    fields=["towplane", "start_tach", "end_tach", "fuel_added", "notes"],
    extra=0,
    widgets={
        "notes": TinyMCE(mce_attrs={"height": 300}),
    }
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only show club-owned and active gliders and towplanes
        self.fields["glider"].queryset = Glider.objects.filter(club_owned=True, is_active=True)
        self.fields["towplane"].queryset = Towplane.objects.filter(is_active=True)

