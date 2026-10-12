from django.db import migrations, models
from django.db.models import Count
from django.db.models.functions import Lower


def reject_existing_duplicate_emails(apps, schema_editor):
    Member = apps.get_model("members", "Member")
    duplicates = list(
        Member.objects.using(schema_editor.connection.alias)
        .exclude(email="")
        .annotate(normalized_email=Lower("email"))
        .values("normalized_email")
        .annotate(member_count=Count("pk"))
        .filter(member_count__gt=1)
    )
    if duplicates:
        raise RuntimeError(
            "Cannot add case-insensitive member email uniqueness while duplicate "
            f"addresses exist ({len(duplicates)} duplicate groups). Resolve the "
            "duplicate member emails, then rerun migrations."
        )


class Migration(migrations.Migration):
    dependencies = [
        ("members", "0031_merge_profile_rebuild_heads"),
        ("members", "0031_migrate_legacy_contact_redaction"),
    ]

    operations = [
        migrations.RunPython(
            reject_existing_duplicate_emails,
            migrations.RunPython.noop,
        ),
        migrations.AddConstraint(
            model_name="member",
            constraint=models.UniqueConstraint(
                models.functions.Lower("email"),
                condition=~models.Q(email=""),
                name="members_member_email_ci_unique",
            ),
        ),
    ]
