# Unit Tests in the Members App

This document describes the unit tests for the `members` app.

## Overview
- Tests cover member creation, authentication, profile editing, badge assignment, and group logic.
- Tests are located in `members/tests.py`.

## Test Coverage
- Member creation and profile logic
- Authentication (including Google OAuth2 pipeline)
- Badge assignment and display
- Biography editing and upload
- Group/role assignment and permissions
- Decorator logic (e.g., `active_member_required`)
- **Membership Application System (Issue #245):**
  - Application form submission and validation
  - International address and foreign pilot support
  - Status transitions and workflow management
  - Administrative review interface functionality
  - User-initiated withdrawal with notifications
  - Management command cleanup operations

## Redaction tests
- The redaction feature (toggle visibility and notification creation) is covered by tests in `members/tests/` including `test_toggle_redaction.py` and `test_notifications_on_toggle.py`.


## Also See
- [README.md](README.md)
- [models.md](models.md)
- [decorators.md](decorators.md)
- [pipeline.md](pipeline.md)
- [views.md](views.md)
- [management.md](management.md)
- [forms.md](forms.md)
