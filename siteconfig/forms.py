from django import forms
from django.core.exceptions import ValidationError

from members.constants.membership import US_STATE_CHOICES
from members.models import Member


class VisitingPilotSignupForm(forms.Form):
    """Quick signup form for visiting pilots."""

    first_name = forms.CharField(
        max_length=30,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "First Name",
                "required": True,
            }
        ),
    )

    last_name = forms.CharField(
        max_length=30,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Last Name",
                "required": True,
            }
        ),
    )

    email = forms.EmailField(
        widget=forms.EmailInput(
            attrs={
                "class": "form-control",
                "placeholder": "Email Address",
                "required": True,
            }
        )
    )

    phone = forms.CharField(
        max_length=15,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Phone Number (optional)",
                "type": "tel",
            }
        ),
    )

    ssa_member_number = forms.CharField(
        max_length=10,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "SSA Member Number (if applicable)",
                "pattern": "[0-9]*",
            }
        ),
    )

    glider_rating = forms.ChoiceField(
        choices=[("", "Select Rating (if applicable)")] + Member.GLIDER_RATING_CHOICES,
        required=False,
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    home_club = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Home Club/Organization (optional)",
            }
        ),
    )

    # Optional glider information
    glider_n_number = forms.CharField(
        max_length=20,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "N-Number (e.g., N12345) - optional",
            }
        ),
        help_text="If you're bringing your own glider, please provide its N-number",
    )

    glider_make = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Make (e.g., Schleicher) - optional",
            }
        ),
    )

    glider_model = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Model (e.g., ASK-21) - optional",
            }
        ),
    )

    def clean_email(self):
        """Check if email is already in use."""
        email = self.cleaned_data.get("email")
        if email and Member.objects.filter(email=email).exists():
            raise ValidationError(
                "This email address is already registered. If you've flown with us before, "
                'go back and choose "I\'ve flown here before" instead of this form.'
            )
        return email

    def clean_ssa_member_number(self):
        """Validate SSA member number format if provided."""
        ssa_number = self.cleaned_data.get("ssa_member_number")
        if ssa_number:
            # Remove any spaces or dashes
            ssa_number = ssa_number.replace(" ", "").replace("-", "")

            # Check if it's all digits and not zero
            if not ssa_number.isdigit():
                raise ValidationError("SSA member number should contain only numbers.")

            # Prevent "0" as SSA number
            if ssa_number == "0":
                raise ValidationError(
                    "SSA member number cannot be '0'. Please enter your actual SSA member number."
                )

            # Note: Duplicate checking moved to clean() method for better coordination with name checking

        return ssa_number

    def clean(self):
        """Custom validation based on site configuration."""
        cleaned_data = super().clean()

        # Import here to avoid circular imports
        from .models import SiteConfiguration

        try:
            config = SiteConfiguration.objects.first()
            if not config or not config.visiting_pilot_enabled:
                raise ValidationError(
                    "Visiting pilot registration is currently disabled."
                )

            errors = []

            # Check SSA requirement
            if config.visiting_pilot_require_ssa and not cleaned_data.get(
                "ssa_member_number"
            ):
                errors.append("SSA membership number is required for visiting pilots.")

            # Check rating requirement
            if config.visiting_pilot_require_rating and not cleaned_data.get(
                "glider_rating"
            ):
                errors.append("Glider rating is required for visiting pilots.")

            # Check for duplicate members by name and SSA combination
            first_name = cleaned_data.get("first_name")
            last_name = cleaned_data.get("last_name")
            ssa_number = cleaned_data.get("ssa_member_number")

            # First check if SSA number is already in use (most definitive check)
            if ssa_number:
                existing_with_ssa = Member.objects.filter(
                    SSA_member_number=ssa_number
                ).first()
                if existing_with_ssa:
                    errors.append(
                        f"You appear to already be registered as {existing_with_ssa.first_name} {existing_with_ssa.last_name} "
                        f"with SSA #{existing_with_ssa.SSA_member_number}. If this is you, go back and choose "
                        f'"I\'ve flown here before" instead of this form.'
                    )

            # Then check for name matches (only if SSA check didn't find a duplicate)
            elif first_name and last_name:
                existing_by_name = Member.objects.filter(
                    first_name__iexact=first_name, last_name__iexact=last_name
                ).first()

                if existing_by_name:
                    if existing_by_name.SSA_member_number:
                        # Existing member has SSA number, new person doesn't - could be different people
                        errors.append(
                            f"A member named {existing_by_name.first_name} {existing_by_name.last_name} is already registered "
                            f"with SSA #{existing_by_name.SSA_member_number}. If this is you, go back and choose "
                            f'"I\'ve flown here before" instead of this form. '
                            f"If you're a different person with the same name, please contact the duty officer."
                        )
                    else:
                        # Both members lack SSA numbers - needs human verification
                        errors.append(
                            f"A member named {existing_by_name.first_name} {existing_by_name.last_name} is already registered. "
                            f'If this is you, go back and choose "I\'ve flown here before" instead of this form. '
                            f"Otherwise, please contact the duty officer for assistance."
                        )

            # Validate glider information if provided
            cleaned_data = _clean_glider_fields(cleaned_data, errors)

            if errors:
                raise ValidationError(errors)

        except SiteConfiguration.DoesNotExist:
            raise ValidationError(
                "Site configuration not found. Please contact the duty officer."
            )

        return cleaned_data


def _clean_glider_fields(cleaned_data, errors, exclude_n_number=None):
    """Shared 'all-three-or-none' + duplicate-N-number validation for glider fields."""
    glider_n_number = (cleaned_data.get("glider_n_number") or "").strip()
    glider_make = (cleaned_data.get("glider_make") or "").strip()
    glider_model = (cleaned_data.get("glider_model") or "").strip()

    cleaned_data["glider_n_number"] = glider_n_number
    cleaned_data["glider_make"] = glider_make
    cleaned_data["glider_model"] = glider_model

    glider_fields_count = sum(
        1 for field in (glider_n_number, glider_make, glider_model) if field
    )

    if glider_fields_count > 0 and glider_fields_count < 3:
        errors.append(
            "If you're providing glider information, please fill in all glider fields "
            "(N-Number, Make, and Model)."
        )
    elif glider_fields_count == 3:
        from logsheet.models import Glider

        normalized_n = glider_n_number.upper()
        cleaned_data["glider_n_number"] = normalized_n

        existing_glider = Glider.objects.filter(n_number__iexact=normalized_n)
        if exclude_n_number:
            existing_glider = existing_glider.exclude(n_number__iexact=exclude_n_number)
        if existing_glider.exists():
            errors.append(
                f"A glider with N-number {normalized_n} is already registered in the system."
            )

    return cleaned_data


class VisitingPilotLookupForm(forms.Form):
    """'Have you flown with us before?' lookup, keyed on email only (Issue #1017).

    Email-only (rather than name) lookup is a deliberate security choice: the daily
    QR token is shared with everyone at the field, so allowing a name-based search
    would let anyone browse for/impersonate an existing member's record.
    """

    email = forms.EmailField(
        widget=forms.EmailInput(
            attrs={
                "class": "form-control",
                "placeholder": "Email Address",
                "required": True,
                "autofocus": True,
            }
        )
    )


class VisitingPilotReturningUpdateForm(forms.Form):
    """Lets a returning visiting pilot refresh their contact info and check in again."""

    phone = forms.CharField(
        max_length=20,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Phone Number",
                "type": "tel",
            }
        ),
    )
    mobile_phone = forms.CharField(
        max_length=20,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Mobile Phone Number",
                "type": "tel",
            }
        ),
    )
    address = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={"class": "form-control", "rows": 2, "placeholder": "Street Address"}
        ),
    )
    city = forms.CharField(
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "City"}),
    )
    state_code = forms.ChoiceField(
        choices=[("", "Select State")] + US_STATE_CHOICES,
        required=False,
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    zip_code = forms.CharField(
        max_length=10,
        required=False,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "ZIP Code"}
        ),
    )
    ssa_member_number = forms.CharField(
        max_length=10,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "SSA Member Number (if applicable)",
                "pattern": "[0-9]*",
            }
        ),
    )
    glider_rating = forms.ChoiceField(
        choices=[("", "Select Rating (if applicable)")] + Member.GLIDER_RATING_CHOICES,
        required=False,
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    home_club = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "Home Club/Organization"}
        ),
    )
    glider_n_number = forms.CharField(
        max_length=20,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "N-Number (e.g., N12345) - optional",
            }
        ),
        help_text="If you're bringing your own glider, please provide its N-number",
    )
    glider_make = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Make (e.g., Schleicher) - optional",
            }
        ),
    )
    glider_model = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Model (e.g., ASK-21) - optional",
            }
        ),
    )

    def __init__(self, *args, member=None, **kwargs):
        self.member = member
        super().__init__(*args, **kwargs)

    def clean_ssa_member_number(self):
        """Validate SSA member number format if provided."""
        ssa_number = self.cleaned_data.get("ssa_member_number")
        if ssa_number:
            ssa_number = ssa_number.replace(" ", "").replace("-", "")
            if not ssa_number.isdigit():
                raise ValidationError("SSA member number should contain only numbers.")
            if ssa_number == "0":
                raise ValidationError(
                    "SSA member number cannot be '0'. Please enter your actual SSA member number."
                )
            existing = Member.objects.filter(SSA_member_number=ssa_number)
            if self.member:
                existing = existing.exclude(pk=self.member.pk)
            if existing.exists():
                raise ValidationError(
                    "That SSA member number is already registered to a different member."
                )
        return ssa_number

    def clean(self):
        cleaned_data = super().clean()
        errors = []
        exclude_n_number = None
        submitted_n_number = (cleaned_data.get("glider_n_number") or "").strip().upper()
        if (
            self.member
            and submitted_n_number
            and self.member.gliders_owned.filter(
                n_number__iexact=submitted_n_number
            ).exists()
        ):
            exclude_n_number = submitted_n_number
        cleaned_data = _clean_glider_fields(
            cleaned_data, errors, exclude_n_number=exclude_n_number
        )
        if errors:
            raise ValidationError(errors)
        return cleaned_data
