# Pipeline Logic in the Members App

The `members/pipeline.py` file defines custom authentication and profile pipelines, primarily for Google OAuth2 integration. This is unique to the `members` app because member onboarding and profile enrichment require custom steps not needed in other apps.

## Why a Pipeline?
- **Purpose:**
  - To customize user creation, username assignment, and profile enrichment during authentication.
  - To fetch and store Google profile pictures, set default membership status, and debug pipeline data.
- **Why Only in Members?**
  - Only the `members` app handles authentication and user profile creation directly.
  - Other apps rely on the user model but do not manage authentication flows.

## Pipeline Functions
- `debug_pipeline_data`: Logs pipeline data for debugging.
- `create_username`: Ensures unique usernames for new members.
- `set_default_membership_status`: Sets initial status for new members.
- `fetch_google_profile_picture`: Downloads and stores Google profile images.

## Also See
- [README.md](README.md)
- [models.md](models.md)
- [decorators.md](decorators.md)
- [views.md](views.md)
- [management.md](management.md)
- [tests.md](tests.md)
- [forms.md](forms.md)
