# Views in the Members App

This document describes the main views provided by the `members` app.

## Member Views
- `member_list(request)`: Lists all members, with filtering and search.
- `member_view(request, member_id)`: Displays a single member's profile.
- `biography_view(request, member_id)`: Shows and edits a member's biography.
- `home(request)`: Member dashboard/homepage.
- `set_password(request)`: Allows members to set or reset their password.
- `tinymce_image_upload(request)`: Handles image uploads for rich text fields.
- `badge_board(request)`: Displays all badges and member achievements.

## Also See
- [README.md](README.md)
- [models.md](models.md)
- [decorators.md](decorators.md)
- [pipeline.md](pipeline.md)
- [management.md](management.md)
- [tests.md](tests.md)
- [forms.md](forms.md)
