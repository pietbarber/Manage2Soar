from django import forms
from django.core.exceptions import ValidationError

from .models import Biography, Member
from .utils.image_processing import generate_profile_thumbnails

#########################
# MemberProfilePhotoForm Class

# Form for uploading or updating a member's profile photo.
# Used in the member directory or personal settings.
# Automatically generates medium (200x200) and small (64x64) thumbnails.

# Meta:
# - model: Member
# - fields: only includes profile_photo


class MemberProfilePhotoForm(forms.ModelForm):
    class Meta:
        model = Member
        fields = ["profile_photo"]

    def save(self, commit=True):
        """
        Save the profile photo and generate thumbnails.

        Generates both medium (200x200) and small (64x64) square thumbnails
        for efficient display in member lists and navigation.
        """
        instance = super().save(commit=False)

        # Check if a new photo was uploaded
        if "profile_photo" in self.changed_data and self.cleaned_data.get(
            "profile_photo"
        ):
            uploaded_file = self.cleaned_data["profile_photo"]

            try:
                # Generate all image sizes
                thumbnails = generate_profile_thumbnails(uploaded_file)

                # Save original (it's already handled by the form, but we use
                # the processed version for consistency)
                instance.profile_photo.save(
                    uploaded_file.name, thumbnails["original"], save=False
                )

                # Save medium thumbnail
                medium_name = f"medium_{uploaded_file.name}"
                instance.profile_photo_medium.save(
                    medium_name, thumbnails["medium"], save=False
                )

                # Save small thumbnail
                small_name = f"small_{uploaded_file.name}"
                instance.profile_photo_small.save(
                    small_name, thumbnails["small"], save=False
                )
            except ValueError as e:
                # Re-raise as validation error so it shows in form
                raise ValidationError(str(e))

        if commit:
            instance.save()

        return instance


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
    new_password1 = forms.CharField(label="New password", widget=forms.PasswordInput)
    new_password2 = forms.CharField(
        label="Confirm new password", widget=forms.PasswordInput
    )

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get("new_password1")
        p2 = cleaned_data.get("new_password2")
        if p1 and p2 and p1 != p2:
            raise ValidationError("Passwords do not match.")
        return cleaned_data
