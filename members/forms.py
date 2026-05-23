import logging

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import PasswordResetForm, _unicode_ci_compare
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives
from django.template import loader
from tinymce.widgets import TinyMCE

from .models import Biography, Member, SafetyReport
from .utils.image_processing import generate_profile_thumbnails

logger = logging.getLogger(__name__)

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

                # Save medium thumbnail (upload path function adds directory prefix)
                instance.profile_photo_medium.save(
                    uploaded_file.name, thumbnails["medium"], save=False
                )

                # Save small thumbnail (upload path function adds directory prefix)
                instance.profile_photo_small.save(
                    uploaded_file.name, thumbnails["small"], save=False
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


class DevModePasswordResetForm(PasswordResetForm):
    """Password reset form with OAuth account support.

    Password reset emails intentionally bypass EMAIL_DEV_MODE redirection so the
    member who requested access always receives the reset link directly.
    """

    def get_users(self, email):
        """Return active users matching email, including OAuth-only accounts.

        Django's default PasswordResetForm excludes users with unusable passwords.
        In this project, many members authenticate via OAuth first and therefore
        start with an unusable local password. They should still be able to use
        "Forgot your password?" to bootstrap a local password.
        """
        email_field_name = get_user_model().get_email_field_name()
        active_users = get_user_model()._default_manager.filter(
            **{
                f"{email_field_name}__iexact": email,
                "is_active": True,
            }
        )
        return (
            user
            for user in active_users
            if _unicode_ci_compare(email, getattr(user, email_field_name))
        )

    def send_mail(
        self,
        subject_template_name,
        email_template_name,
        context,
        from_email,
        to_email,
        html_email_template_name=None,
    ):
        subject = loader.render_to_string(subject_template_name, context)
        subject = "".join(subject.splitlines())
        body = loader.render_to_string(email_template_name, context)

        email_message = EmailMultiAlternatives(
            subject=subject,
            body=body,
            from_email=from_email,
            to=[to_email],
        )

        if html_email_template_name is not None:
            html_email = loader.render_to_string(html_email_template_name, context)
            email_message.attach_alternative(html_email, "text/html")

        try:
            email_message.send()
        except Exception:
            logger.exception(
                "Failed to send password reset email for recipient: %s",
                to_email,
            )


#########################
# SafetyReportForm Class

# Form for submitting safety observations.
# Members can optionally submit anonymously.

# Related: Issue #554 - Add Safety Report form accessible to any member


class SafetyReportForm(forms.ModelForm):
    """Form for members to submit safety observations."""

    class Meta:
        model = SafetyReport
        fields = ["observation", "observation_date", "location", "is_anonymous"]
        widgets = {
            "observation": TinyMCE(
                attrs={
                    "cols": 80,
                    "rows": 10,
                    "placeholder": "Describe what you observed...",
                },
            ),
            "observation_date": forms.DateInput(
                attrs={
                    "type": "date",
                    "class": "form-control",
                },
            ),
            "location": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "e.g., Runway, Launch area, Tie-down area",
                },
            ),
            "is_anonymous": forms.CheckboxInput(
                attrs={
                    "class": "form-check-input",
                },
            ),
        }
        labels = {
            "observation": "What did you observe?",
            "observation_date": "When did this occur? (optional)",
            "location": "Where did this occur? (optional)",
            "is_anonymous": "Submit anonymously",
        }
        help_texts = {
            "observation": "Describe the safety concern in as much detail as possible.",
            "is_anonymous": (
                "If checked, your identity will not be recorded with this report. "
                "Be honest - anonymous reports are taken seriously."
            ),
        }


# SafetyReportOfficerForm Class

# Form for safety officers to update report status, notes, and actions taken.
# Related: Issue #585 - Safety Officer Interface


class SafetyReportOfficerForm(forms.ModelForm):
    """Form for safety officers to update safety reports."""

    class Meta:
        model = SafetyReport
        fields = ["status", "officer_notes", "actions_taken"]
        widgets = {
            "status": forms.Select(
                attrs={
                    "class": "form-select",
                },
            ),
            "officer_notes": TinyMCE(
                attrs={
                    "cols": 80,
                    "rows": 6,
                },
            ),
            "actions_taken": TinyMCE(
                attrs={
                    "cols": 80,
                    "rows": 6,
                },
            ),
        }
        labels = {
            "status": "Report Status",
            "officer_notes": "Internal Notes (not visible to reporter)",
            "actions_taken": "Actions Taken",
        }
        help_texts = {
            "officer_notes": "These notes are only visible to safety officers.",
            "actions_taken": "Describe what actions were taken to address this concern.",
        }
