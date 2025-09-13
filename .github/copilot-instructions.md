# Copilot Instructions for Manage2Soar

## Project Overview
- **Manage2Soar** is a Django 5.2 web application for soaring club management: members, gliders, badges, operations, analytics, and instruction.
- Major apps: `members`, `logsheet`, `duty_roster`, `instructors`, `analytics`, `cms`, `knowledgetest`.
- Data flows between apps via Django ORM models and signals. Analytics is read-only, built on `logsheet` and `members` data.

## Key Workflows
- **Run locally:**
  ```bash
  python3 -m venv env && source env/bin/activate
  pip install -r requirements.txt
  python manage.py migrate
  python manage.py runserver
  ```
- **Tests:**
  - Use `pytest` (preferred) or `python manage.py test`.
  - Test config: `pytest.ini`, per-app `tests.py`.
- **Static files:**
  - Collect with `python manage.py collectstatic`.
- **ERD generation:**
  - Requires `graphviz` system package.
  - Run: `python generate_erds.py`

## Project Conventions
- **Authentication:** Google OAuth2 (default), fallback to Django login.
- **Role-based access:** Permissions via Django groups; see `members`, `duty_roster`.
- **Rich text:** Uses `django-tinymce` for bios, instruction, essays.
- **Analytics:** All charts are read-only, exportable (PNG/SVG/CSV), see `analytics/README.md`.
- **Operations:** Flight logs (`logsheet`), duty roster (`duty_roster`), and instruction (`instructors`) are tightly integrated.
- **Email notifications:** Automated for operations, reminders, and ad-hoc events.

## Patterns & Structure
- **App structure:** Each app has `models.py`, `views.py`, `admin.py`, `urls.py`, and `tests.py`.
- **Templates:** Per-app in `templates/`; global in `templates/` root.
- **Docs:** See per-app `docs/` folders and main `README.md`.
- **Data import/export:** Use Django admin or custom scripts in `loaddata/`.
- **Custom logic:** See `duty_roster/roster_generator.py`, `analytics/queries.py`, `instructors/utils.py`.

## Integration & Dependencies
- **External:** Google OAuth2, Chart.js (frontend), Graphviz (ERD), Pillow, qrcode, vobject, django-reversion, django-htmx.
- **Internal:** Cross-app model relations, signals, and shared templates.

## Examples
- To add a new analytics chart: update `analytics/queries.py` and corresponding template.
- To add a new member field: update `members/models.py`, run migrations, update forms/admin.
- To customize duty roster logic: see `duty_roster/roster_generator.py`.

---
For more, see `README.md` and per-app `README.md`/`docs/` folders. When in doubt, follow Django best practices unless project docs specify otherwise.
