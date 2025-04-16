
import io

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django import forms
from datetime import date, timedelta
from PIL import Image
from tinymce.widgets import TinyMCE
from .utils.image_processing import resize_and_crop_profile_photo
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Fieldset, Row, Column, Submit

from .models import Badge, Biography, Member, MemberBadge, Biography

#########################
# MemberProfilePhotoForm Class

# Form for uploading or updating a member’s profile photo.
# Used in the member directory or personal settings.

# Meta:
# - model: Member
# - fields: only includes profile_photo

class MemberProfilePhotoForm(forms.ModelForm):
    class Meta:
        model = Member
        fields = ['profile_photo']

#########################
# BiographyForm Class

# Form for creating or editing a member's rich text biography.
# Supports HTML input and optional image embedding via TinyMCE.

# Meta:
# - model: Biography
# - fields: includes body (HTML content of the biography)

class BiographyForm(forms.ModelForm):
    class Meta:
        model = Biography
        fields = ["content"]

#########################
# SetPasswordForm Class

# Custom form for allowing a logged-in user to set or update their password.
# Used when transitioning from OAuth to username/password authentication.

# Fields:
# - new_password1: new password
# - new_password2: confirmation of new password

# Methods:
# - clean(): validates that the two passwords match

class SetPasswordForm(forms.Form):
    new_password1 = forms.CharField(
        label="New password",
        widget=forms.PasswordInput
    )
    new_password2 = forms.CharField(
        label="Confirm new password",
        widget=forms.PasswordInput
    )

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get("new_password1")
        p2 = cleaned_data.get("new_password2")
        if p1 and p2 and p1 != p2:
            raise ValidationError("Passwords do not match.")
        return cleaned_data
