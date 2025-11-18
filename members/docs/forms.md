# Forms in the Members App

This document describes the forms defined in `members/forms.py` and `members/forms_applications.py` and their purpose in the app.

## Member Profile Forms (`members/forms.py`)

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

## Membership Application Forms (`members/forms_applications.py`)

### `MembershipApplicationForm`
- **Type:** `ModelForm`
- **Purpose:** Handles membership applications from non-logged-in users (Issue #245).
- **Model:** `MembershipApplication`
- **Fields:** Comprehensive application including personal info, aviation experience, club history.
- **Features:**
  - International address support with country-specific field requirements
  - Foreign pilot support with conditional validation
  - Bootstrap 5 styling with responsive design
  - Custom validation for aviation experience fields
  - Dynamic state/province requirements based on country selection

### `MembershipApplicationReviewForm`
- **Type:** `ModelForm`
- **Purpose:** Administrative form for reviewing membership applications.
- **Model:** `MembershipApplication`
- **Fields:** Review actions (approve, reject, waitlist, withdraw), admin notes, waitlist position.
- **Features:**
  - Status management with proper workflow transitions
  - Member account creation for approved applications
  - Administrative notes and review tracking
  - Waitlist position management

## Also See
- [README.md](README.md)
- [models.md](models.md)
- [decorators.md](decorators.md)
- [pipeline.md](pipeline.md)
- [views.md](views.md)
- [management.md](management.md)
- [tests.md](tests.md)
