from django import forms
from datetime import date, timedelta
from .models import Member
from tinymce.widgets import TinyMCE
from .utils.image_processing import resize_and_crop_profile_photo
from django.core.files.base import ContentFile
from django.core.exceptions import ValidationError
from PIL import Image
import io

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Field
from crispy_forms.layout import Layout, Fieldset, Row, Column, Submit

class MemberForm(forms.ModelForm):
    class Meta:
        model = Member
        fields = [
          'membership_status',
          'username', 
         
          'email',
          'legacy_username', 'SSA_member_number', 'phone', 'mobile_phone',

          'first_name', 'middle_initial', 'nickname', 'last_name', 'name_suffix',
          'country', 'state_code', 'state_freeform',
          'address',
          'city',
          'zip_code',
          'profile_photo',
          'glider_rating', 'instructor', 'towpilot', 'duty_officer', 'assistant_duty_officer', 'secretary',
          'treasurer', 'webmaster', 'director', 'member_manager',
          'glider_owned',
          'second_glider_owned',
          'joined_club',
          'emergency_contact',
          'public_notes',
          'private_notes',
          'last_updated_by'
        ]

        widgets = {
            'address': forms.Textarea(attrs={'rows': 2}),
            'emergency_contact': forms.Textarea(attrs={'rows': 2}),
            'public_notes': TinyMCE(attrs={'rows': 10}),
            'private_notes': TinyMCE(attrs={'rows': 10}),
        }
    
    def clean_profile_photo(self):
        photo = self.cleaned_data.get("profile_photo")

        if not photo:
            return photo

        # Load image and check dimensions
        try:
            image = Image.open(photo)
            width, height = image.size

            # Aspect ratio check: no panoramas, no skyscrapers
            aspect_ratio = width / height
            if aspect_ratio > 2.0:
                raise ValidationError("Image too wide — please upload a square-ish photo.")
            elif aspect_ratio < 0.5:
                raise ValidationError("Image too tall — please upload a square-ish photo.")
        except Exception as e:
            raise ValidationError("Invalid image uploaded.")
        return photo



    def save(self, commit=True):
        instance = super().save(commit=False)

        uploaded_photo = self.cleaned_data.get("profile_photo")

        if uploaded_photo:
            try:
                resized_image = resize_and_crop_profile_photo(uploaded_photo)

                # Build safe filename based on username and original extension
                extension = uploaded_photo.name.split('.')[-1]
                filename = f"profile_{instance.username}.{extension}"

                instance.profile_photo.save(filename, resized_image, save=False)

            except ValueError as e:
                self.add_error("profile_photo", str(e))
                raise  # Re-raise to stop saving if invalid

        if commit:
            instance.save()
            self.save_m2m()

        return instance


    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_method = 'post'

        self.helper.layout = Layout(
            # You can include other fields before this…
    
            Fieldset(
                'Location Info',
                Row(
                    Column('country', css_class='form-group col-md-6 mb-0'),
                ),
                Row(
                    Column('state_code', css_class='form-group col-md-6 mb-0', css_id='state-code-wrapper'),
                    Column('state_freeform', css_class='form-group col-md-6 mb-0', css_id='state-freeform-wrapper'),
                ),
            ),

            # Followed by other fields or buttons
            Submit('submit', 'Save changes')
        )


        # 📅 Restrict joined_club date to reasonable range
        today = date.today()
        min_date = date(1990, 1, 1)
        max_date = today + timedelta(days=30)

        self.fields['joined_club'].widget = forms.DateInput(
            attrs={
                'class': 'form-control',
                'min': min_date.isoformat(),
                'max': max_date.isoformat(),
            },
            format='%Y-%m-%d'
        )
        self.fields['username'].disabled = True
        self.fields['username'].help_text = "Usernames are not editable."


        # Remove default verbose help text for system fields
        for field in ['username', 'email', 'first_name', 'last_name']:
            self.fields[field].help_text = None

        self.fields['profile_photo'].help_text = "Upload a clear, smiling portrait. 😄"
        self.fields['public_notes'].help_text = "Visible to all members."
        self.fields['private_notes'].help_text = "Visible only to club officers."
        self.fields['legacy_username'].help_text = "User handle that was used on old web server"

from .models import MemberBadge

class MemberBadgeForm(forms.ModelForm):
    class Meta:
        model = MemberBadge
        fields = ['badge', 'date_awarded', 'notes']
        widgets = {
            'date_awarded': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }

from django import forms
from tinymce.widgets import TinyMCE
from .models import Badge

class BadgeForm(forms.ModelForm):
    description = forms.CharField(widget=TinyMCE(attrs={'rows': 10}))
    class Meta:
        model = Badge
        fields = '__all__'

class MemberProfilePhotoForm(forms.ModelForm):
    class Meta:
        model = Member
        fields = ['profile_photo']


from .models import Biography

class BiographyForm(forms.ModelForm):
    class Meta:
        model = Biography
        fields = ['content', 'uploaded_image']
        widgets = {
            'content': TinyMCE(attrs={'cols': 80, 'rows': 30}),
        }


from django import forms
from .models import FlightLog

import json
class FlightLogForm(forms.ModelForm):
    class Meta:
        model = FlightLog
        fields = [
            'flight_date',
            'airfield',
            'glider',
            'pilot',
            'instructor',
            'passenger',
            'towplane',
            'towpilot',
            'release_altitude',
            'takeoff_time',
            'landing_time',
            'flight_time',
            'alternate_payer',
            'pays',
        ]
        flight_time = forms.CharField(
            required=False,
            widget=forms.TextInput(attrs={
                'readonly': 'readonly',
                'class': 'form-control bg-light text-muted ghost-field',
                'placeholder': 'hh:mm',
                'tabindex': '-1',  # Skip this field when tabbing through the form
            })
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['instructor'].queryset = Member.objects.filter(instructor=True)

        from .models import Glider  # local import to avoid circular imports
        glider_seats = {glider.id: glider.number_of_seats for glider in Glider.objects.all()}
        self.fields['glider'].widget.attrs['data-gliders'] = json.dumps(glider_seats)

        self.fields['flight_date'].widget = forms.DateInput(
            attrs={'type': 'text', 'class': 'form-control'},
            format='%Y-%m-%d'
        )

        self.fields['takeoff_time'].widget = forms.TimeInput(
            attrs={'type': 'text', 'class': 'form-control'},
            format='%H:%M'
        )

        self.fields['landing_time'].widget = forms.TimeInput(
            attrs={'type': 'text', 'class': 'form-control'},
            format='%H:%M'
        )

        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            'flight_date',
            'airfield',
            'glider',
            'pilot',
            'instructor',
            'passenger',
            'towplane',
            'towpilot',
            'release_altitude',
            'takeoff_time',
            'landing_time',
            Field('flight_time', readonly=True),
            'alternate_payer',
            'pays',
            Submit('submit', 'Save Flight')
        )

from django import forms
from .models import FlightDay
from django.forms import HiddenInput

class FlightDayForm(forms.ModelForm):
    class Meta:
        model = FlightDay
        fields = ['flight_date', 'airfield', 'duty_officer', 'assistant', 'instructor', 'towpilot']
        widgets = {
            'date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-control'
            }, format='%Y-%m-%d')
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        import datetime
        self.fields['flight_date'].initial = datetime.date.today()
        self.fields['duty_officer'].queryset = Member.objects.filter(duty_officer=True)
        self.fields['instructor'].queryset = Member.objects.filter(instructor=True)
        self.fields['towpilot'].queryset = Member.objects.filter(towpilot=True)
        self.fields['flight_date'].widget = forms.HiddenInput()

