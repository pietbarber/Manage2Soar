from django.db import migrations

CONTACT_FIELDS = ("email", "phone", "address")


def migrate_legacy_contact_redaction(apps, schema_editor):
    Member = apps.get_model("members", "Member")
    for member in Member.objects.filter(redact_contact=True).iterator():
        visibility = (
            dict(member.contact_visibility)
            if isinstance(member.contact_visibility, dict)
            else {}
        )
        visibility.update({field: "hide" for field in CONTACT_FIELDS})
        member.contact_visibility = visibility
        member.redact_contact = False
        member.save(update_fields=["contact_visibility", "redact_contact"])


def reverse_migrate_legacy_contact_redaction(apps, schema_editor):
    # Conservative rollback: restore the legacy full-redaction override only for
    # records whose three contact fields are all explicitly hidden. This is the
    # exact signature written by the forward migration, so reverting a release
    # re-hides those members rather than exposing them. Members with any field
    # not set to "hide" are left untouched (their per-field preference stands).
    Member = apps.get_model("members", "Member")
    for member in Member.objects.iterator():
        visibility = (
            member.contact_visibility
            if isinstance(member.contact_visibility, dict)
            else None
        )
        if visibility is not None and all(
            visibility.get(field) == "hide" for field in CONTACT_FIELDS
        ):
            member.redact_contact = True
            member.save(update_fields=["redact_contact"])


class Migration(migrations.Migration):
    dependencies = [
        ("members", "0030_merge_20261005_2055"),
    ]

    operations = [
        migrations.RunPython(
            migrate_legacy_contact_redaction,
            reverse_migrate_legacy_contact_redaction,
        ),
    ]
