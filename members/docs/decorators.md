# Decorators in the Members App

This document describes the decorators defined in `members/decorators.py` and their usage throughout the app.

## Decorators

### `active_member_required`
- **Purpose:** Restricts access to views so that only active members can access them.
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
