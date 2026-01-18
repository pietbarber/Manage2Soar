# Decorators in the Members App

This document describes the decorators defined in `members/decorators.py` and their usage throughout the app.

## Decorators

### `active_member_required`
- **Purpose:** Restricts access to views so that only active members can access them.
- **Special Cases:**
  - **Kiosk Sessions (Issue #486):** Users authenticated via kiosk tokens bypass membership_status checks, allowing role accounts (like "Club Laptop") to access member-only views.
  - **Superusers:** Superusers always pass this check regardless of membership_status.
- **Usage:**
  - Applied to views that require the user to be an active member (e.g., profile editing, badge board).
  - Wraps the view function, checks member status, and redirects or raises permission errors as needed.
- **Example:**
  ```python
  @active_member_required
  def member_dashboard(request):
      ...
  ```

## Also See
- [README.md](README.md)
- [models.md](models.md)
- [pipeline.md](pipeline.md)
- [views.md](views.md)
- [management.md](management.md)
- [tests.md](tests.md)
- [forms.md](forms.md)
