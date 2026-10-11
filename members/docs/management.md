# Management Commands & Legacy Data Import

This document describes the management commands for the `members` app, especially those used to import data from the legacy database. It also documents the structure of the legacy tables used in these imports.

## Management Commands

### Legacy Data Import Commands
- `import_members_only`: Imports member records from the legacy `members` table.
- `import_member_biographies`: Imports biographies from the legacy `bios` table.
- `import_member_badges`: Imports badge awards from the legacy `badges_earned` and `badge_link` tables.
- `import_member_photos`: Imports member profile photos from CSV (not from legacy DB).
- `export_member_photos`: Command for exporting member photos.

### Membership Application Management Commands
- `cleanup_approved_applications`: Removes approved membership applications older than 365 days to maintain data retention policies.
- `cleanup_applications_cronjob`: CronJob version of application cleanup with distributed locking for Kubernetes environments.

**Note:** The cleanup commands preserve all application data for 365 days before removal, ensuring adequate time for record-keeping and administrative review.

## Administrator Member CSV

Both member CSV export paths include an `emergency_contacts` column containing a
JSON array. Each contact object contains `name`, `relationship`, `home_phone`,
`mobile_phone`, `preferred_contact_method`, `preferred_contact_details`, and
`address`. For example:

```json
[{"name":"Jane Doe","relationship":"Spouse","home_phone":"555-0100","mobile_phone":"","preferred_contact_method":"home_phone","preferred_contact_details":"Call after 5","address":""}]
```

The member import resource reads this column and replaces the member's
structured contacts with the listed contacts. An empty array (`[]`) removes all
structured contacts. CSV imports without the column leave existing structured
contacts unchanged. The legacy `emergency_contact` column remains available
for compatibility.

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
