from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models

from .models_applications import MembershipApplication


class MembershipApplicationForm(forms.ModelForm):
    """
    Form for membership applications from non-logged-in users.
    Based on the legacy PDF membership application form.
    """

    # Custom widget choices for better UX
    GLIDER_RATING_WIDGET_CHOICES = [
        ("none", "None / Not a pilot"),
        ("student", "Student pilot"),
        ("transition", "Transition training"),
        ("private", "Private pilot - Glider"),
        ("commercial", "Commercial pilot - Glider"),
        ("foreign", "Foreign pilot"),
    ]

    # Country choices - most common countries for soaring clubs
    COUNTRY_CHOICES = [
        ("USA", "United States"),
        ("CAN", "Canada"),
        ("GBR", "United Kingdom"),
        ("AUS", "Australia"),
        ("DEU", "Germany"),
        ("FRA", "France"),
        ("NZL", "New Zealand"),
        ("CHE", "Switzerland"),
        ("AUT", "Austria"),
        ("NLD", "Netherlands"),
        ("SWE", "Sweden"),
        ("NOR", "Norway"),
        ("DNK", "Denmark"),
        ("FIN", "Finland"),
        ("ESP", "Spain"),
        ("ITA", "Italy"),
        ("POL", "Poland"),
        ("CZE", "Czech Republic"),
        ("HUN", "Hungary"),
        ("SVK", "Slovakia"),
        ("SVN", "Slovenia"),
        ("HRV", "Croatia"),
        ("ROU", "Romania"),
        ("BGR", "Bulgaria"),
        ("GRC", "Greece"),
        ("PRT", "Portugal"),
        ("BEL", "Belgium"),
        ("LUX", "Luxembourg"),
        ("IRL", "Ireland"),
        ("ARG", "Argentina"),
        ("BRA", "Brazil"),
        ("CHL", "Chile"),
        ("ZAF", "South Africa"),
        ("JPN", "Japan"),
        ("KOR", "South Korea"),
        ("SGP", "Singapore"),
        ("OTHER", "Other (please specify in comments)"),
    ]

    # Override country field as ChoiceField to ensure proper dropdown rendering
    country = forms.ChoiceField(
        choices=COUNTRY_CHOICES,
        initial="USA",
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    class Meta:
        model = MembershipApplication
        fields = [
            # Personal Information
            "first_name",
            "middle_initial",
            "last_name",
            "name_suffix",
            "email",
            "phone",
            "mobile_phone",
            "address_line1",
            "address_line2",
            "city",
            "state",
            "zip_code",
            "country",
            # Emergency Contact
            "emergency_contact_name",
            "emergency_contact_relationship",
            "emergency_contact_phone",
            # Aviation Experience
            "pilot_certificate_number",
            "glider_rating",
            "has_private_pilot",
            "has_commercial_pilot",
            "has_cfi",
            "total_flight_hours",
            "glider_flight_hours",
            "recent_flight_hours",
            "ssa_member_number",
            # History
            "previous_club_memberships",
            "previous_member_at_this_club",
            "previous_membership_details",
            "insurance_rejection_history",
            "insurance_rejection_details",
            "club_rejection_history",
            "club_rejection_details",
            "aviation_incidents",
            "aviation_incident_details",
            # Goals and Interests
            "soaring_goals",
            "availability",
            # Agreement
            "agrees_to_terms",
            "agrees_to_safety_rules",
            "agrees_to_financial_obligations",
            # Additional
            "additional_comments",
        ]

        widgets = {
            # Personal Information
            "first_name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "First Name",
                    "required": True,
                }
            ),
            "middle_initial": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "M", "maxlength": 2}
            ),
            "last_name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Last Name",
                    "required": True,
                }
            ),
            "name_suffix": forms.Select(attrs={"class": "form-select"}),
            "email": forms.EmailInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "your.email@example.com",
                    "required": True,
                }
            ),
            "phone": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "(555) 123-4567",
                    "required": True,
                }
            ),
            "mobile_phone": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "(555) 123-4567"}
            ),
            # Address
            "address_line1": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Street Address (e.g., 123 Main St or 1-2-3 Ginza)",
                    "required": True,
                }
            ),
            "address_line2": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Apartment, Suite, Ward, District, etc.",
                }
            ),
            "city": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "City, Town, or Prefecture",
                    "required": True,
                }
            ),
            "state": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "State/Province (required for US addresses)",
                }
            ),
            "zip_code": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "ZIP/Postal Code (required for US addresses)",
                }
            ),
            "country": forms.Select(attrs={"class": "form-select"}),
            # Emergency Contact
            "emergency_contact_name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Full Name",
                    "required": True,
                }
            ),
            "emergency_contact_relationship": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "e.g., Spouse, Parent, Sibling",
                    "required": True,
                }
            ),
            "emergency_contact_phone": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "(555) 123-4567",
                    "required": True,
                }
            ),
            # Aviation Experience
            "pilot_certificate_number": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "FAA Certificate Number (US pilots only)",
                }
            ),
            "glider_rating": forms.Select(attrs={"class": "form-select"}),
            "total_flight_hours": forms.NumberInput(
                attrs={"class": "form-control", "min": 0, "placeholder": "0"}
            ),
            "glider_flight_hours": forms.NumberInput(
                attrs={"class": "form-control", "min": 0, "placeholder": "0"}
            ),
            "recent_flight_hours": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "min": 0,
                    "placeholder": "Hours in last 24 months",
                }
            ),
            "ssa_member_number": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "SSA Member Number (if applicable)",
                }
            ),
            # History - Text areas
            "previous_club_memberships": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "List any previous soaring club memberships, including club names and years of membership",
                }
            ),
            "previous_membership_details": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Please provide details about your previous membership at this club (years active, reason for leaving, etc.)",
                }
            ),
            "insurance_rejection_details": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Please explain the circumstances of any insurance rejection",
                }
            ),
            "club_rejection_details": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Please explain the circumstances of any club membership rejection",
                }
            ),
            "aviation_incident_details": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Please provide details of any aviation incidents or accidents",
                }
            ),
            # Goals and Interests
            "soaring_goals": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": "What are your goals with soaring? What interests you about our club?",
                    "required": True,
                }
            ),
            "availability": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "When are you typically available? (e.g., weekends, specific days, seasons)",
                }
            ),
            # Additional Comments
            "additional_comments": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Any additional information you'd like to share with us",
                }
            ),
        }

        labels = {
            "first_name": "First Name",
            "middle_initial": "Middle Initial",
            "last_name": "Last Name",
            "name_suffix": "Suffix",
            "email": "Email Address",
            "phone": "Primary Phone",
            "mobile_phone": "Mobile Phone",
            "address_line1": "Street Address",
            "address_line2": "Address Line 2",
            "city": "City",
            "state": "State/Province",
            "zip_code": "ZIP/Postal Code",
            "country": "Country",
            "emergency_contact_name": "Emergency Contact Name",
            "emergency_contact_relationship": "Relationship",
            "emergency_contact_phone": "Emergency Contact Phone",
            "pilot_certificate_number": "FAA Pilot Certificate Number",
            "glider_rating": "Current Glider Rating",
            "has_private_pilot": "Private Pilot Certificate",
            "has_commercial_pilot": "Commercial Pilot Certificate",
            "has_cfi": "Certified Flight Instructor - Glider (CFI-G)",
            "total_flight_hours": "Total Flight Hours (All Aircraft)",
            "glider_flight_hours": "Glider Flight Hours",
            "recent_flight_hours": "Recent Flight Hours (Last 24 Months)",
            "ssa_member_number": "SSA Member Number",
            "previous_club_memberships": "Previous Club Memberships",
            "previous_member_at_this_club": "Have you ever been a member of this club before?",
            "previous_membership_details": "Previous Membership Details",
            "insurance_rejection_history": "Have you ever been rejected for aviation insurance?",
            "insurance_rejection_details": "Insurance Rejection Details",
            "club_rejection_history": "Have you ever been rejected for club membership?",
            "club_rejection_details": "Club Rejection Details",
            "aviation_incidents": "Have you been involved in aviation incidents/accidents?",
            "aviation_incident_details": "Aviation Incident Details",
            "soaring_goals": "Your Soaring Goals and Interest in Our Club",
            "availability": "Availability for Club Activities",
            "agrees_to_terms": "I agree to abide by all club rules and regulations",
            "agrees_to_safety_rules": "I agree to follow all club safety procedures",
            "agrees_to_financial_obligations": "I agree to meet all financial obligations as a club member",
            "additional_comments": "Additional Comments",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Override glider rating choices for better display
        self.fields["glider_rating"].choices = self.GLIDER_RATING_WIDGET_CHOICES

        # Make agreement fields required
        self.fields["agrees_to_terms"].required = True
        self.fields["agrees_to_safety_rules"].required = True
        self.fields["agrees_to_financial_obligations"].required = True

        # Make soaring goals required
        self.fields["soaring_goals"].required = True

        # Make aviation experience fields optional for beginners
        self.fields["glider_rating"].required = False
        self.fields["total_flight_hours"].required = False
        self.fields["glider_flight_hours"].required = False
        self.fields["recent_flight_hours"].required = False
        self.fields["pilot_certificate_number"].required = False

    def clean_email(self):
        """Validate email and ensure it's not already in use."""
        email = self.cleaned_data.get("email")
        if email:
            # Check if email is already used by an existing member
            from members.models import Member

            if Member.objects.filter(email__iexact=email).exists():
                raise ValidationError(
                    "This email address is already registered. If you already have an account, "
                    "please log in instead of submitting a new application."
                )

            # Check if there's already a pending application with this email
            existing_app = MembershipApplication.objects.filter(
                email__iexact=email,
                status__in=[
                    "pending",
                    "under_review",
                    "additional_info_needed",
                    "waitlisted",
                ],
            ).first()
            if existing_app:
                raise ValidationError(
                    f"There is already a pending membership application for this email address "
                    f"(submitted on {existing_app.submitted_at.strftime('%B %d, %Y')}). "
                    f"Please contact our membership managers if you have questions."
                )

        return email

    def clean(self):
        """Validate form data and handle conditional requirements."""
        cleaned_data = super().clean()

        # Validate agreement checkboxes
        if not cleaned_data.get("agrees_to_terms"):
            raise ValidationError("You must agree to the club terms and conditions.")
        if not cleaned_data.get("agrees_to_safety_rules"):
            raise ValidationError("You must agree to follow club safety rules.")
        if not cleaned_data.get("agrees_to_financial_obligations"):
            raise ValidationError("You must agree to meet financial obligations.")

        # If insurance rejection is checked, details are required
        if cleaned_data.get("insurance_rejection_history") and not cleaned_data.get(
            "insurance_rejection_details"
        ):
            raise ValidationError(
                {
                    "insurance_rejection_details": "Please explain the insurance rejection circumstances."
                }
            )

        # If club rejection is checked, details are required
        if cleaned_data.get("club_rejection_history") and not cleaned_data.get(
            "club_rejection_details"
        ):
            raise ValidationError(
                {
                    "club_rejection_details": "Please explain the club rejection circumstances."
                }
            )

        # If aviation incidents is checked, details are required
        if cleaned_data.get("aviation_incidents") and not cleaned_data.get(
            "aviation_incident_details"
        ):
            raise ValidationError(
                {
                    "aviation_incident_details": "Please provide details about the aviation incidents."
                }
            )

        # Validate address fields based on country
        country = cleaned_data.get("country") or "USA"
        if country == "USA":
            # For US addresses, state and zip are required
            if not cleaned_data.get("state"):
                self.add_error("state", "State is required for US addresses.")
            if not cleaned_data.get("zip_code"):
                self.add_error("zip_code", "ZIP code is required for US addresses.")
        else:
            # For non-US addresses, state and zip are optional
            # Update field labels to be more generic
            pass

        # If they have pilot certificates, validate certificate number (except foreign pilots)
        glider_rating = cleaned_data.get("glider_rating") or "none"
        if not cleaned_data.get("glider_rating"):
            cleaned_data["glider_rating"] = "none"
        has_any_rating = any(
            [
                cleaned_data.get("has_private_pilot"),
                cleaned_data.get("has_commercial_pilot"),
                cleaned_data.get("has_cfi"),
                glider_rating not in ["none", ""],
            ]
        )
        is_foreign_pilot = glider_rating == "foreign"

        # Only require FAA certificate number for US pilots with ratings
        if (
            has_any_rating
            and not is_foreign_pilot
            and not cleaned_data.get("pilot_certificate_number")
        ):
            self.add_error(
                "pilot_certificate_number",
                "Please provide your FAA pilot certificate number since you indicated you have US pilot ratings.",
            )

        # Validate flight hours make sense (provide defaults for missing values)
        total_hours = cleaned_data.get("total_flight_hours")
        glider_hours = cleaned_data.get("glider_flight_hours")
        recent_hours = cleaned_data.get("recent_flight_hours")

        # Set defaults if not provided
        if total_hours is None:
            cleaned_data["total_flight_hours"] = 0
            total_hours = 0
        if glider_hours is None:
            cleaned_data["glider_flight_hours"] = 0
            glider_hours = 0
        if recent_hours is None:
            cleaned_data["recent_flight_hours"] = 0
            recent_hours = 0

        # Ensure country has a default value
        if not cleaned_data.get("country"):
            cleaned_data["country"] = "USA"

        # Only validate relationships if values are provided
        if glider_hours > total_hours:
            self.add_error(
                "glider_flight_hours", "Glider hours cannot exceed total flight hours."
            )

        if recent_hours > total_hours:
            self.add_error(
                "recent_flight_hours", "Recent hours cannot exceed total flight hours."
            )

        return cleaned_data


class MembershipApplicationReviewForm(forms.ModelForm):
    """
    Form for membership managers to review and make decisions on applications.
    """

    REVIEW_ACTIONS = [
        ("", "--- Select Action ---"),
        ("approve", "Approve Application"),
        ("waitlist", "Add to Waiting List"),
        ("need_info", "Request Additional Information"),
        ("reject", "Reject Application"),
    ]

    review_action = forms.ChoiceField(
        choices=REVIEW_ACTIONS,
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    class Meta:
        model = MembershipApplication
        fields = ["status", "admin_notes", "waitlist_position"]
        widgets = {
            "status": forms.Select(attrs={"class": "form-select"}),
            "admin_notes": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": "Private notes for membership managers (not visible to applicant)",
                }
            ),
            "waitlist_position": forms.NumberInput(
                attrs={"class": "form-control", "min": 1}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Status is handled by review_action, not directly by the form
        self.fields["status"].required = False
        self.fields["status"].widget = forms.HiddenInput()

        # If on waitlist, show position field
        if self.instance and self.instance.status == "waitlisted":
            self.fields["waitlist_position"].widget.attrs["readonly"] = False
        else:
            self.fields["waitlist_position"].widget = forms.HiddenInput()

    def clean(self):
        """Validate review form data."""
        cleaned_data = super().clean()
        review_action = cleaned_data.get("review_action")
        admin_notes = cleaned_data.get("admin_notes", "").strip()

        # If requesting more info, require admin notes explaining what's needed
        if review_action == "need_info" and not admin_notes:
            raise ValidationError(
                {
                    "admin_notes": "Please explain what additional information is needed from the applicant."
                }
            )

        # If adding to waitlist, position is required
        if review_action == "waitlist" and not cleaned_data.get("waitlist_position"):
            # Auto-assign next position if not provided
            from .models_applications import MembershipApplication

            max_position = MembershipApplication.objects.filter(
                status="waitlisted"
            ).aggregate(max_pos=models.Max("waitlist_position"))["max_pos"]
            cleaned_data["waitlist_position"] = (max_position or 0) + 1

        return cleaned_data
