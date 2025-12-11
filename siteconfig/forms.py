from django import forms
from django.core.exceptions import ValidationError

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
                "This email address is already registered. Please contact the duty officer if you need assistance."
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
                        f"with SSA #{existing_with_ssa.SSA_member_number}. Please contact the duty officer for assistance."
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
                            f"with SSA #{existing_by_name.SSA_member_number}. If this is you, please provide your SSA number. "
                            f"If you're a different person with the same name, please contact the duty officer."
                        )
                    else:
                        # Both members lack SSA numbers - needs human verification
                        errors.append(
                            f"A member named {existing_by_name.first_name} {existing_by_name.last_name} is already registered. "
                            f"Please provide your SSA member number to help us distinguish between members, "
                            f"or contact the duty officer if you need assistance."
                        )

            # Validate glider information if provided
            glider_n_number = cleaned_data.get("glider_n_number")
            glider_make = cleaned_data.get("glider_make")
            glider_model = cleaned_data.get("glider_model")

            # If any glider field is provided, require all three
            glider_fields_provided = [glider_n_number, glider_make, glider_model]
            glider_fields_count = sum(1 for field in glider_fields_provided if field)

            if glider_fields_count > 0 and glider_fields_count < 3:
                errors.append(
                    "If you're providing glider information, please fill in all glider fields (N-Number, Make, and Model)."
                )

            # Check if glider N-number already exists
            if glider_n_number:
                from logsheet.models import Glider

                # Normalize N-number for comparison and save back to cleaned_data
                normalized_n = glider_n_number.strip().upper()
                cleaned_data["glider_n_number"] = normalized_n

                # Use exact comparison since we've already normalized to uppercase
                if Glider.objects.filter(n_number=normalized_n).exists():
                    errors.append(
                        f"A glider with N-number {normalized_n} is already registered in the system."
                    )

            if errors:
                raise ValidationError(errors)

        except SiteConfiguration.DoesNotExist:
            raise ValidationError(
                "Site configuration not found. Please contact the duty officer."
            )

        return cleaned_data
