# Management Commands for knowledgetest

This page documents all custom Django management commands in `knowledgetest/management/commands/`.

---

## `import_legacy_tests`

**Filename:** `import_legacy_tests.py`
**Purpose:** Imports legacy written-test questions and categories from a legacy database into the current app.

**Usage:**
```bash
python manage.py import_legacy_tests
```
- Connects to the legacy database as defined in `settings.DATABASES['legacy']`.
- Imports question categories and questions.
- Handles Windows-1252 encoding.
- Skips questions with unknown categories.

---

## Also See
- [README (App Overview)](README.md)
- [Models](models.md)
- [Forms](forms.md)
- [Views](views.md)
