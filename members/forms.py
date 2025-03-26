from django import forms
from datetime import date, timedelta
from .models import Member
from tinymce.widgets import TinyMCE
from .utils.image_processing import resize_and_crop_profile_photo
from django.core.files.base import ContentFile
from django.core.exceptions import ValidationError
from PIL import Image
import io


class MemberForm(forms.ModelForm):
    joined_club = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'form-control',
        }),
        input_formats=['%Y-%m-%d']
    )
    class Meta:
        model = Member
        fields = [
          'membership_status',
          'username', 
         
          'email',
          'legacy_username', 'SSA_member_number', 'phone', 'mobile_phone',

          'first_name', 'middle_initial', 'nickname', 'last_name', 'name_suffix',

          'address',
          'city',
          'state',
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

        # 📅 Restrict joined_club date to reasonable range
        today = date.today()
        min_date = date(1990, 1, 1)
        max_date = today + timedelta(days=30)

        self.fields['joined_club'].widget = forms.DateInput(
            attrs={
                'type': 'date',
                'class': 'form-control',
                'min': min_date.isoformat(),
                'max': max_date.isoformat(),
            },
            format='%Y-%m-%d'
        )
        self.fields['joined_club'].input_formats = ['%Y-%m-%d']
        self.fields['username'].disabled = True


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
