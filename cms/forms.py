from django import forms
from tinymce.widgets import TinyMCE

from .models import SiteFeedback


class SiteFeedbackForm(forms.ModelForm):
    class Meta:
        model = SiteFeedback
        fields = ['feedback_type', 'subject', 'message']
        widgets = {
            'feedback_type': forms.Select(attrs={'class': 'form-select'}),
            'subject': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Brief description of the issue or request'
            }),
            'message': TinyMCE(attrs={
                'cols': 80,
                'rows': 10,
                'class': 'form-control'
            }),
        }
        labels = {
            'feedback_type': 'Type of Feedback',
            'subject': 'Subject',
            'message': 'Details',
        }
        help_texts = {
            'message': 'Please provide as much detail as possible to help us understand and address your feedback.',
        }
