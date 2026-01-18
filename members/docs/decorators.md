# Decorators in the Members App

This document describes the decorators defined in `members/decorators.py` and their usage throughout the app.

## Decorators

### `active_member_required`
- **Purpose:** Restricts access to views so that only active members can access them.
- **Special Cases:**
  - **Kiosk Sessions (Issue #486):** When the `is_kiosk_authenticated` session flag is set (by KioskAutoLoginMiddleware or kiosk bind view), this decorator bypasses membership_status checks for the request, allowing role accounts (like "Club Laptop") to access member-only views without a valid membership_status field. Users are still authenticated as normal Django users by the kiosk middleware; the session flag indicates kiosk authentication, not the cookies themselves.
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
