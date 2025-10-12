# Views in knowledgetest/views.py

This document summarizes all classes and functions in `knowledgetest/views.py`.

---

## Main Functions
- **_get_empty_preset()**: Helper to return an empty test preset.
- **get_presets()**: Returns available test presets for use in test creation.

## Main Classes
- **WrittenTestStartView (TemplateView)**: Displays the start page for a written test.
- **AssignmentPermissionMixin**: Mixin to check assignment permissions for test views.
- **CreateWrittenTestView (FormView)**: Allows instructors to create a new written test for a student.
- **WrittenTestSubmitView (View)**: Handles POST submission of a written test attempt.
- **WrittenTestResultView (DetailView)**: Shows the results of a completed written test attempt.
- **PendingTestsView (ListView)**: Lists all pending written test assignments for a user.

---

## Also See
- [README (App Overview)](README.md)
- [Models](models.md)
- [Forms](forms.md)
- [Management Commands](management.md)
