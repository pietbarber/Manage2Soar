
from django import forms
from .models import Logsheet

class CreateLogsheetForm(forms.ModelForm):
    class Meta:
        model = Logsheet
        fields = ["log_date", "location"]
        widgets = {
            "log_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "location": forms.TextInput(attrs={"class": "form-control"}),
        }
