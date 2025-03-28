
from django import forms
from django.core.exceptions import ValidationError
from .models import Logsheet

class CreateLogsheetForm(forms.ModelForm):
    class Meta:
        model = Logsheet
        fields = ["log_date", "location"]
        widgets = {
            "log_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "location": forms.TextInput(attrs={"class": "form-control"}),
        }

    def clean(self):
        cleaned_data = super().clean()
        log_date = cleaned_data.get("log_date")
        location = cleaned_data.get("location")

        if log_date and location:
            if Logsheet.objects.filter(log_date=log_date, location=location).exists():
                raise ValidationError("A logsheet for this date and location already exists.")

        return cleaned_data

from django import forms
from .models import Flight

class FlightForm(forms.ModelForm):
    class Meta:
        model = Flight
        fields = [
            "launch_time",
            "landing_time",
            "pilot",
            "instructor",
            "glider",
            "tow_pilot",
            "field",
            "flight_type",
            "notes",
        ]
        widgets = {
            "launch_time": forms.TimeInput(attrs={"type": "time", "class": "form-control"}),
            "landing_time": forms.TimeInput(attrs={"type": "time", "class": "form-control"}),
            "pilot": forms.Select(attrs={"class": "form-select"}),
            "instructor": forms.Select(attrs={"class": "form-select"}),
            "glider": forms.Select(attrs={"class": "form-select"}),
            "tow_pilot": forms.Select(attrs={"class": "form-select"}),
            "field": forms.TextInput(attrs={"class": "form-control"}),
            "flight_type": forms.TextInput(attrs={"class": "form-control"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }
