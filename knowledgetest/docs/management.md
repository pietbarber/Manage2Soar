
# Management Commands for knowledgetest

This page documents all custom Django management commands in `knowledgetest/management/commands/`.

---

## Legacy Database Reference

When importing historical test data, the following legacy tables are used as sources:

### qcodes
Defines question categories for written tests.

| Column      | Type    | Description                |
|-------------|---------|----------------------------|
| qcode       | varchar | Category code (PK)         |
| description | text    | Category description       |

### test_contents
Stores individual written test questions and answers.

| Column       | Type    | Description                        |
|--------------|---------|------------------------------------|
| qnum         | int     | Question number (PK)                |
| code         | varchar | Category code (FK to qcodes.qcode)  |
| question     | text    | Question text                       |
| a            | text    | Answer option A                     |
| b            | text    | Answer option B                     |
| c            | text    | Answer option C                     |
| d            | text    | Answer option D                     |
| answer       | text    | Correct answer (A/B/C/D)            |
| explanation  | text    | Explanation for the answer          |
| lastupdated  | date    | Last updated date                   |
| updatedby    | text    | Last updated by (username)          |

---

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
