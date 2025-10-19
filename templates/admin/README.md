Admin template overrides
=======================

This directory contains a project-level override of Django's admin `change_list.html`.

Why this exists
---------------
We inject a small helper message into admin changelist pages when a `ModelAdmin` sets
an `admin_helper_message` attribute. To make this automatic for all apps we copied
the upstream Django `admin/change_list.html` template into the project and inserted
a single include to render the helper fragment:

  {% include "admin/_admin_helper.html" %}

Location and source
-------------------
- Project override: `templates/admin/change_list.html`
- Helper fragment: `templates/admin/_admin_helper.html`
- Upstream source: copied from the installed Django package on this machine at
  the time of the change. If you need to rebase or update the override, locate
  the packaged template in your environment (e.g. `$VENV/lib/pythonX.Y/site-packages/django/contrib/admin/templates/admin/change_list.html`).

Upgrading Django
-----------------
When upgrading Django, compare the new upstream `admin/change_list.html` with
this override and merge any important changes. Typically this will be needed when
major or minor Django releases change the admin markup or add new template
blocks. Steps:

1. Find the new upstream template in the new Django package.
2. Use a three-way merge or `diff` to apply any changes, keeping our single
   insertion point for the helper include.
3. Run the test suite and spot-check the admin UI.

Maintenance note
----------------
We deliberately keep the helper fragment `admin/_admin_helper.html` separate so
the visual markup is in one place and easy to change. If you prefer to inline
the markup into `change_list.html` you can do so, but leaving it as an include
keeps the override minimal.
