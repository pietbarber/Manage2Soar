from django import forms
from .models import Member

class MemberForm(forms.ModelForm):
    class Meta:
        model = Member
        fields = [
            "username", "email", "first_name", "last_name",  # default user fields
            "SSA_member_number", "phone", "address", "city", "state", "zip_code",
            "glider_rating", "is_instructor", "is_duty_officer", "is_assistant_duty_officer",
            "secretary", "treasurer", "webmaster", "glider_owned", "second_glider_owned",
            "joined_club", "emergency_contact", "public_notes", "private_notes"
        ]
        widgets = {
            'SSA_member_number': forms.TextInput(attrs={'placeholder': 'SSA Member Number'}),
            'first_name': forms.TextInput(attrs={'placeholder': 'First Name'}),
            'last_name': forms.TextInput(attrs={'placeholder': 'Last Name'}),
            'email': forms.EmailInput(attrs={'placeholder': 'Email'}),
            'phone': forms.TextInput(attrs={'placeholder': 'Phone'}),
            'address': forms.Textarea(attrs={'placeholder': 'Address'}),
            'city': forms.TextInput(attrs={'placeholder': 'City'}),
            'state': forms.TextInput(attrs={'placeholder': 'State'}),
            'zip_code': forms.TextInput(attrs={'placeholder': 'Zip Code'}),
        }
        labels = {
            'SSA_member_number': 'SSA Member Number',
            'first_name': 'First Name',
            'last_name': 'Last Name',
            'email': 'Email',
            'phone': 'Phone',
            'address': 'Address',
            'city': 'City',
            'state': 'State',
            'zip_code': 'Zip Code',
        }
        help_texts = {
            'SSA_member_number': 'Enter the SSA member number.',
            'first_name': 'Enter the first name of the member.',
            'last_name': 'Enter the last name of the member.',
            'email': 'Enter a valid email address.',
            'phone': 'Enter the phone number.',
            'address': 'Enter the address.',
            'city': 'Enter the city.',
            'state': 'Enter the state.',
            'zip_code': 'Enter the zip code.',
        }
        error_messages = {
            'SSA_member_number': {
                'required': 'SSA Member Number is required.',
                'unique': 'This SSA Member Number is already in use.',
            },
            'email': {
                'required': 'Email is required.',
                'invalid': 'Enter a valid email address.',
            },
        }
        # Add any additional validation or customization as needed
        # Example: custom validation for unique SSA member number   
        def clean_SSA_member_number(self):
            SSA_member_number = self.cleaned_data.get('SSA_member_number')
            if Member.objects.exclude(pk=self.instance.pk).filter(SSA_member_number=SSA_member_number).exists():
                raise forms.ValidationError("This SSA Member Number is already in use.")
            return SSA_member_number
        # Example: custom validation for email
        def clean_email(self):
            email = self.cleaned_data.get('email')
            if Member.objects.exclude(pk=self.instance.pk).filter(email=email).exists():
                raise forms.ValidationError("This email is already in use.")
            return email
        # Example: custom validation for membership status
        def clean_membership_status(self):
            membership_status = self.cleaned_data.get('membership_status')
            if membership_status not in ['Full Member', 'Student Member', 'Inactive']:
                raise forms.ValidationError("Invalid membership status.")
            return membership_status