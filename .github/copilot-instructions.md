# Copilot Instructions for Manage2Soar

## Project Overview
- **Manage2Soar** is a Django 5.2 web application for soaring club management: members, gliders, badges, operations, analytics, and instruction.
- Major apps: `members`, `logsheet`, `duty_roster`, `instructors`, `analytics`, `cms`, `knowledgetest`, `notifications`, `siteconfig`, `utils`.
- **Production deployment:** Kubernetes cluster with 2-pod deployment, PostgreSQL database, distributed CronJob system.

## Terminal Environment Setup
- **CRITICAL**: Every new terminal window requires virtual environment activation. The first command in any new terminal session MUST be:
  ```bash
  source .venv/bin/activate
  ```
- **Issue**: New terminal windows do not automatically source the virtual environment, causing Python/pytest/Django commands to fail with "command not found" errors.
- **Solution**: Always run `source .venv/bin/activate` as the first command when starting any terminal operation.
- **Commands that require venv**: `pytest`, `python manage.py`, `pip`, `django-admin`, `black`, `isort`, `bandit`, `safety`, and any Python-related tooling.

## Terminal Window Management
- **UNPREDICTABLE**: VS Code's `run_in_terminal` tool unpredictably creates new terminal windows vs reusing existing ones. This cannot be controlled or predicted.
- **BEST PRACTICES**:
  1. **Always prefix Python commands**: Use `source .venv/bin/activate && your_command` when uncertain
  2. **Check environment first**: Run `which python` to verify virtual environment before Python operations
  3. **Expect new terminals**: Background processes, long-running commands, and time gaps between commands often spawn new terminals
- **WORKFLOW**: When you see "command not found" errors, immediately run `source .venv/bin/activate` and retry the command.

## Django Development Server Management
- **CRITICAL PORT REQUIREMENT**: Development server MUST run on port 8001 due to HSTS cache issues on port 8000. NEVER use port 8001 in production.
- **DEVELOPMENT SERVER COMMAND**: Always use `python manage.py runserver 127.0.0.1:8001` for local development
- **CHECK FIRST**: Before starting `manage.py runserver`, always check if it's already running on port 8001:
  ```bash
  lsof -i :8001 || echo "Port 8001 is free"
  ```
- **HSTS ISSUE**: Port 8000 has persistent HSTS cache (365 days) that forces HTTPS, breaking local development. Port 8001 avoids this issue.
- **AUTO-RESTART**: Django's development server automatically restarts when you modify `.py` files (views.py, models.py, forms.py, etc.). You do NOT need to manually restart it.
- **AUTO-RESTART**: Django's development server automatically handles restarts when Python files change. This works regardless of your editor.
- **WHEN TO RESTART**: Only manually restart the server for:
  - New dependencies/packages installed
  - Settings changes (manage2soar/settings.py)
  - Template/static file changes (sometimes)
  - Migration changes that affect the database schema
- **AVOID**: Don't use `pkill` or `lsof` commands to kill existing servers unless explicitly needed. VS Code will manage the auto-restart process.

## Additional Context Resources
- **Conversation Archives**: For complex issues requiring deep context, check `.github/conversations/` for saved debugging sessions and technical discussions. These contain valuable insights about system architecture, problem-solving approaches, data migration patterns, and testing strategies.
- **IMPORTANT**: The `.github/conversations/` directory is gitignored - these files exist locally only and provide rich historical context for understanding technical decisions and debugging complex issues.

## GitHub Issue Lookup
- **CRITICAL**: When user references an issue by number (e.g., "work on issue 70"), use this MCP pattern:
  - **Method 1 (Preferred)**: `mcp_github_github_list_issues` with `owner="pietbarber"`, `repo="Manage2Soar"`, `state="OPEN"` to get all open issues, then filter for the specific number
  - **Method 2 (Fallback)**: `mcp_github_github_search_issues` with `owner="pietbarber"`, `repo="Manage2Soar"`, `query="[issue_number]"` (simple number only, no GitHub syntax)
- **DO NOT USE**:
  - `mcp_github_github_get_issue` (tool doesn't exist)
  - GitHub search syntax like `"number:70"` or `"is:issue 70"` (fails in search)
- This eliminates the "three different attempts" pattern - use Method 1 first, then Method 2 if needed.
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

## CSS & Static Files Management
- **CRITICAL**: Always run `python manage.py collectstatic` after making changes to CSS files in `static/` directories. Changes to CSS files are NOT visible until collected.
- **CSS Architecture**:
  - Use external CSS files in `static/css/` instead of inline `<style>` tags in templates
  - Check existing CSS in `static/css/baseline.css` for conflicting rules before creating new styles
  - CSS specificity issues can cause "styling not working" problems - use browser dev tools to inspect actual applied styles
  - When CSS "isn't working", check: 1) `collectstatic` was run, 2) CSS selectors match actual HTML elements, 3) specificity conflicts with existing CSS
- **CSS Debugging Process**:
  1. Make CSS changes in `static/css/` files
  2. Run `python manage.py collectstatic --noinput`
  3. Test in browser (hard refresh with Ctrl+F5 to clear cache)
  4. Use browser dev tools to verify CSS is actually being applied
  5. If still not working, check for CSS specificity conflicts with existing rules

## Troubleshooting
- If you see `NoReverseMatch`, check that the URL name exists in your `urls.py`.
- If you see 404s in tests, verify that the URL is actually implemented and included.
- If content assertions fail, ensure the test data matches the view's query logic (e.g., correct slug and audience).
- **CSS Issues**: If styling appears broken, always check if `collectstatic` was run after CSS changes.
- **CRITICAL**: After any changes to `urls.py` (especially CMS routes), immediately run `pytest` to catch broken tests, reverse lookups, and template references.

## Maintenance
- Scaffold new tests for any new models, views, or permission logic.
- Remove or update tests if endpoints or model fields are removed or renamed.
- Use coverage reports to identify and fill gaps in test coverage.
- **URL Changes**: Always run full test suite after modifying `urls.py` - URL changes can break tests, reverse lookups, and CMS content rendering across multiple apps.
- Data flows between apps via Django ORM models and signals. Analytics is read-only, built on `logsheet` and `members` data.

## Key Workflows
- **Run locally:**
  ```bash
  python3 -m venv env && source env/bin/activate
  pip install -r requirements.txt
  python manage.py migrate
  python manage.py runserver 127.0.0.1:8001
  ```
- **Tests:**
  - Use `pytest` (preferred) or `python manage.py test`.
  - Test config: `pytest.ini`, per-app `tests.py`.
- **Static files:**
  - **ALWAYS** collect with `python manage.py collectstatic --noinput` after CSS/JS changes.
  - CSS changes are NOT visible until collected - this is the number one cause of "styling not working" issues.
- **Git commits:**
  - **CRITICAL**: Always run code formatting tools before `git add` to prevent pre-commit hook failures:
    ```bash
    isort .
    black .
    git add .
    git commit -m "Your commit message"
    ```
  - **Tool order matters**: Run `isort` first, then `black` - wrong order causes cascading file changes and commit failures.
  - Pre-commit hooks will automatically run bandit, trailing whitespace fixes, and other checks.
  - If pre-commit hooks modify files, re-add and commit again after the fixes are applied.
- **Database documentation:**
  - Database schemas are documented using Mermaid diagrams in each app's `docs/models.md` files.
  - Mermaid visualizations available as PNG exports (e.g., `erd.png` in project root).
  - See comprehensive workflow documentation at `docs/workflows/` - **essential reading for understanding business processes**.
- **Workflow Integration:**
  - Before making changes, consult `docs/workflows/` to understand how modifications fit into established business processes.
  - Workflows document member lifecycles, operational procedures, and cross-app integrations with detailed Mermaid diagrams.
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
- **Business Process Documentation:** `docs/workflows/` contains detailed Mermaid diagrams showing member lifecycles, operational procedures, and cross-app integrations. **Always consult relevant workflows before implementing changes.**
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
