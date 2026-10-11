# Contact Privacy

Per-field `Member.contact_visibility` preferences are the supported member
privacy controls. Members can independently share or hide their email, phone
numbers, and postal address when the club's `contact_visibility` policy is set
to `direct`. Effective visibility is applied to member profiles, directories,
vCards, and QR contact cards.

## Legacy full redaction

`Member.redact_contact` is retained for compatibility with older data and
views. Migration `0031_migrate_legacy_contact_redaction` converts each
previously redacted member to `hide` for email, phone, and address, then clears
the legacy flag. This preserves the old hide-everything choice in the
per-field settings.

The former full-contact control has been removed. Its endpoint is retained only
to reject old POSTs; it does not change the legacy flag or per-field
preferences. Use the Contact Privacy panel instead. If per-field self-service
is disabled or requires approval, the endpoint rejects the change.

The visibility helpers continue to treat a legacy `redact_contact=True` value
as hidden for non-privileged viewers, in case an older database has not yet
applied the data migration. Members themselves and privileged viewers retain
the visibility exceptions implemented by the contact privacy helpers.

## Testing

Tests should cover per-field visibility, legacy redaction migration, policy
enforcement on both profile controls and direct POST requests, and consistency
across profile, directory, vCard, and QR contact output.
