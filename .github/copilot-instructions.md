# Copilot Instructions for Manage2Soar

## Project Overview
- **Manage2Soar** is a Django 5.2 web application for soaring club management: members, gliders, badges, operations, analytics, and instruction.
- Major apps: `members`, `logsheet`, `duty_roster`, `instructors`, `analytics`, `cms`, `knowledgetest`, `notifications`, `siteconfig`, `utils`.
- **Production deployment:** Kubernetes cluster with 2-pod deployment, PostgreSQL database, distributed CronJob system.
## Testing & Coverage
- All Django apps must have comprehensive test coverage using pytest and pytest-django.
- Use `pytest --cov` or the VS Code "Run test with coverage" feature to ensure all code paths are tested.
- Tests for views must accurately reflect authentication and permission logic. For example, use the `active_member_required` decorator for member-only views, and ensure test users have a valid `membership_status`.
- Do not write tests for public endpoints that do not exist (e.g., `/siteconfig/edit/`); admin-only models should be tested via model logic or Django admin, not via public URLs.
- When updating models or URLs, always update or remove affected tests to prevent false failures.

## URL & View Patterns
- The homepage (`/`) dynamically serves either public or member content based on user status. Do not use redirects for this; render the correct content in-place.
- Use slugs like `"home"` for public content and `"member-home"` for member content in the CMS.
- Only include URLs in `urls.py` that are actually implemented; avoid stubs or placeholders.

## Decorators & Permissions
- Use `active_member_required` for views that require a valid, active member. This decorator checks both authentication and membership status.
- In tests, create users with a valid `membership_status` (e.g., `"Full Member"`) to pass this decorator.

## Troubleshooting
- If you see `NoReverseMatch`, check that the URL name exists in your `urls.py`.
- If you see 404s in tests, verify that the URL is actually implemented and included.
- If content assertions fail, ensure the test data matches the view's query logic (e.g., correct slug and audience).

## Maintenance
- Scaffold new tests for any new models, views, or permission logic.
- Remove or update tests if endpoints or model fields are removed or renamed.
- Use coverage reports to identify and fill gaps in test coverage.
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
- **Database documentation:**
  - Database schemas are documented using Mermaid diagrams in each app's `docs/models.md` files.
  - Mermaid visualizations available as PNG exports (e.g., `erd.png` in project root).
  - See comprehensive workflow documentation at `docs/workflows/`.
- **CronJobs & Scheduled Tasks:**
  - Use `utils.management.commands.base_cronjob.BaseCronJobCommand` for all scheduled tasks.
  - Distributed locking prevents race conditions across multiple Kubernetes pods.
  - See `docs/cronjob-architecture.md` for complete implementation guide.

## Project Conventions
- **Authentication:** Google OAuth2 (default), fallback to Django login.
- **Role-based access:** Permissions via Django groups; see `members`, `duty_roster`.
- **Rich text:** Uses `django-tinymce` for bios, instruction, essays.
- **Analytics:** All charts are read-only, exportable (PNG/SVG/CSV), see `analytics/README.md`.
- **Operations:** Flight logs (`logsheet`), duty roster (`duty_roster`), and instruction (`instructors`) are tightly integrated.
- **Email notifications:** Automated for operations, reminders, and ad-hoc events via distributed CronJob system.
- **Distributed Systems:** PostgreSQL-backed locking for multi-pod coordination, production Kubernetes deployment.

## Patterns & Structure
- **App structure:** Each app has `models.py`, `views.py`, `admin.py`, `urls.py`, and `tests.py`.
- **Templates:** Per-app in `templates/`; global in `templates/` root.
- **Docs:** See per-app `docs/` folders and main `README.md`.
- **Data import/export:** Use Django admin or custom scripts in `loaddata/`.
- **Custom logic:** See `duty_roster/roster_generator.py`, `analytics/queries.py`, `instructors/utils.py`.
- **Scheduled Tasks:** CronJob commands in `*/management/commands/` using `BaseCronJobCommand` framework.

## Integration & Dependencies
- **External:** Google OAuth2, Chart.js (frontend), Pillow, qrcode, vobject, django-reversion, django-htmx.
- **Internal:** Cross-app model relations, signals, and shared templates.

## Examples
- To add a new analytics chart: update `analytics/queries.py` and corresponding template.
- To add a new member field: update `members/models.py`, run migrations, update forms/admin.
- To customize duty roster logic: see `duty_roster/roster_generator.py`.

---
For more, see `README.md` and per-app `README.md`/`docs/` folders. When in doubt, follow Django best practices unless project docs specify otherwise.
