from .models import Logsheet, Airfield
from django.core.exceptions import ValidationError
from django import forms
from django.core.exceptions import ValidationError
from .models import Logsheet, Flight, Towplane
from members.models import Member
from django.utils.timezone import localtime, now

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
        self.fields["towplane"].queryset = Towplane.objects.filter(is_active=True)
        # Filter instructors only
        self.fields["instructor"].queryset = Member.objects.filter(instructor=True)
        self.fields["tow_pilot"].queryset = Member.objects.filter(towpilot=True)
        self.fields["split_with"].queryset = Member.objects.filter(is_active=True).order_by("last_name")
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
        self.fields["duty_officer"].queryset = Member.objects.filter(duty_officer=True).order_by("last_name")
        self.fields["assistant_duty_officer"].queryset = Member.objects.filter(assistant_duty_officer=True).order_by("last_name")
        self.fields["duty_instructor"].queryset = Member.objects.filter(instructor=True).order_by("last_name")
        self.fields["surge_instructor"].queryset = Member.objects.filter(instructor=True).order_by("last_name")
        self.fields["tow_pilot"].queryset = Member.objects.filter(towpilot=True).order_by("last_name")
        self.fields["surge_tow_pilot"].queryset = Member.objects.filter(towpilot=True).order_by("last_name")
        self.fields["default_towplane"].queryset = Towplane.objects.all().order_by("name", "registration")

        # Optional: set widget styles for dropdowns
        for name in [
            "duty_officer", "assistant_duty_officer",
            "duty_instructor", "surge_instructor",
            "tow_pilot", "surge_tow_pilot",
            "default_towplane",
        ]:
            self.fields[name].required = False
            self.fields[name].widget.attrs.update({"class": "form-select"})