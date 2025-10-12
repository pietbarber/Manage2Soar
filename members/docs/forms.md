# Forms in the Members App

This document describes the forms defined in `members/forms.py` and their purpose in the app.

## Forms

### `MemberProfilePhotoForm`
- **Type:** `ModelForm`
- **Purpose:** Handles uploading and updating member profile photos.
- **Model:** `Member`
- **Fields:** Profile photo/image fields.

### `BiographyForm`
- **Type:** `ModelForm`
- **Purpose:** Allows members to edit and submit their biography text.
- **Model:** `Biography`
- **Fields:** Biography text, possibly other metadata.

### `SetPasswordForm`
- **Type:** `Form`
- **Purpose:** Custom form for setting or resetting a member's password.
- **Fields:** Password fields, with custom validation in `clean()`.

## Also See
- [README.md](README.md)
- [models.md](models.md)
- [decorators.md](decorators.md)
- [pipeline.md](pipeline.md)
- [views.md](views.md)
- [management.md](management.md)
- [tests.md](tests.md)
