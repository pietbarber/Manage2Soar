import logging

from django import forms
from tinymce.widgets import TinyMCE

from .models import SiteFeedback, VisitorContact

logger = logging.getLogger(__name__)


class SiteFeedbackForm(forms.ModelForm):
    class Meta:
        model = SiteFeedback
        fields = ["feedback_type", "subject", "message"]
        widgets = {
            "feedback_type": forms.Select(attrs={"class": "form-select"}),
            "subject": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Brief description of the issue or request",
                }
            ),
            "message": TinyMCE(attrs={"cols": 80, "rows": 10, "class": "form-control"}),
        }
        labels = {
            "feedback_type": "Type of Feedback",
            "subject": "Subject",
            "message": "Details",
        }
        help_texts = {
            "message": "Please provide as much detail as possible to help us understand and address your feedback.",
        }


class VisitorContactForm(forms.ModelForm):
    """
    Contact form for visitors (non-members) to reach out to the club.
    Replaces exposing welcome@skylinesoaring.org to spam.

    Includes honeypot field for spam prevention (Issue #590).
    """

    # Honeypot field - bots will fill this, humans won't see it
    # Named 'website' as bots commonly look for this field
    website = forms.CharField(
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Your website",
                "autocomplete": "off",
                "tabindex": "-1",  # Skip in tab order
            }
        ),
        label="Website",
    )

    class Meta:
        model = VisitorContact
        fields = ["name", "email", "phone", "subject", "message"]
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Full name",
                    "required": True,
                }
            ),
            "email": forms.EmailInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "your.email@example.com",
                    "required": True,
                }
            ),
            "phone": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Phone number"}
            ),
            "subject": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Brief subject",
                    "required": True,
                }
            ),
            "message": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 6,
                    "placeholder": "Please tell us how we can help you...",
                    "required": True,
                }
            ),
        }
        labels = {
            "name": "Your Name",
            "email": "Email Address",
            "phone": "Phone Number (Optional)",
            "subject": "Subject",
            "message": "Message",
        }
        help_texts = {
            "message": "Please provide as much detail as possible so we can help you effectively.",
        }

    def clean_email(self):
        """Basic email validation and spam prevention."""
        email = self.cleaned_data.get("email", "").lower()

        # Block obvious spam domains (you can expand this list)
        spam_domains = [
            "tempmail.org",
            "10minutemail.com",
            "guerrillamail.com",
            "mailinator.com",
            "yopmail.com",
        ]

        domain = email.split("@")[-1] if "@" in email else ""
        if domain in spam_domains:
            raise forms.ValidationError(
                "Please use a permanent email address for your inquiry."
            )

        return email

    def clean_message(self):
        """Basic message validation and spam prevention."""
        message = self.cleaned_data.get("message", "")

        # Check for minimum length
        if len(message.strip()) < 10:
            raise forms.ValidationError(
                "Please provide a more detailed message (at least 10 characters)."
            )

        # Basic spam keyword detection
        spam_keywords = [
            "viagra",
            "cialis",
            "casino",
            "lottery",
            "winner",
            "click here",
            "act now",
            "limited time",
            "make money",
            "work from home",
            "guaranteed",
            "risk free",
        ]

        message_lower = message.lower()
        for keyword in spam_keywords:
            if keyword in message_lower:
                raise forms.ValidationError(
                    "Your message contains content that appears to be spam. Please rephrase your inquiry."
                )

        return message

    def clean_website(self):
        """
        Honeypot validation - if this field is filled, it's a bot.
        We don't raise a ValidationError because we want to silently reject.
        Instead, we set a flag that the view can check.
        """
        website = self.cleaned_data.get("website", "")
        if website:
            # Log the honeypot trigger for monitoring
            logger.warning(
                f"Honeypot triggered on contact form. "
                f"Email: {self.data.get('email', 'unknown')}, "
                f"Website field contained: {website[:100]}"
            )
            # Set flag for view to check
            self._honeypot_triggered = True
        else:
            self._honeypot_triggered = False
        return website

    def is_honeypot_triggered(self):
        """Check if the honeypot was triggered."""
        return getattr(self, "_honeypot_triggered", False)
