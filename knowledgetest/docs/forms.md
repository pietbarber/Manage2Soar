# Forms in knowledgetest/forms.py

This document describes all forms in `knowledgetest/forms.py`.

---

## TestSubmissionForm
- **Type:** `forms.Form`
- **Purpose:** Handles user submission of written test answers.
- **Key Methods:**
  - `clean_answers(self)`: Validates the submitted answers field.

## TestBuilderForm
- **Type:** `forms.Form`
- **Purpose:** Used by instructors to build or edit written test templates.
- **Key Methods:**
  - `__init__(self, *args, **kwargs)`: Customizes form initialization for dynamic question sets.

---

## Also See
- [README (App Overview)](README.md)
- [Models](models.md)
- [Views](views.md)
- [Management Commands](management.md)
