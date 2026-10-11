from django.db import migrations


def migrate_legacy_contact_redaction(apps, schema_editor):
    Member = apps.get_model("members", "Member")
    for member in Member.objects.filter(redact_contact=True).iterator():
        visibility = (
            dict(member.contact_visibility)
            if isinstance(member.contact_visibility, dict)
            else {}
        )
        visibility.update({"email": "hide", "phone": "hide", "address": "hide"})
        member.contact_visibility = visibility
        member.redact_contact = False
        member.save(update_fields=["contact_visibility", "redact_contact"])


class Migration(migrations.Migration):
    dependencies = [
        ("members", "0030_merge_20261005_2055"),
    ]

    operations = [
        migrations.RunPython(
            migrate_legacy_contact_redaction,
            migrations.RunPython.noop,
        ),
    ]
