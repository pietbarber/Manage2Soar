# Management Commands & Legacy Data Import

This document describes the management commands for the `members` app, especially those used to import data from the legacy database. It also documents the structure of the legacy tables used in these imports.

## Management Commands
- `import_members_only`: Imports member records from the legacy `members` table.
- `import_member_biographies`: Imports biographies from the legacy `bios` table.
- `import_member_badges`: Imports badge awards from the legacy `badges_earned` and `badge_link` tables.
- `import_member_photos`: Imports member profile photos from CSV (not from legacy DB).
- `export_member_photos`, `sync_sympa`: Other commands for export and mailing list sync.

## Legacy Database Reference

### `members`
- Stores all member profile data in the legacy system.
- **Columns:** handle, first_name, last_name, email, join_date, status, etc.

### `bios`
- Stores member biographies as plain text.
- **Columns:** handle, biography_text, last_updated, etc.

### `badges_earned`
- Tracks which badges each member earned and when.
- **Columns:** handle, badge, earned_date

### `badge_link`
- Maps badge handles to external URLs (e.g., SSA badge links).
- **Columns:** handle, url

## Also See
- [README.md](README.md)
- [models.md](models.md)
- [decorators.md](decorators.md)
- [pipeline.md](pipeline.md)
- [views.md](views.md)
- [tests.md](tests.md)
- [forms.md](forms.md)
