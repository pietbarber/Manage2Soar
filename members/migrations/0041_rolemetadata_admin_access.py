from django.db import migrations, models


CANONICAL_ROLE_KEYS = (
    "instructor_admins",
    "webmasters",
    "member_managers",
    "rostermeisters",
    "secretary",
    "treasurer",
)


def enable_admin_access_for_existing_canonical_roles(apps, schema_editor):
    RoleMetadata = apps.get_model("members", "RoleMetadata")
    RoleMetadata.objects.using(schema_editor.connection.alias).filter(
        key__in=CANONICAL_ROLE_KEYS
    ).update(admin_access=True)


class Migration(migrations.Migration):

    dependencies = [
        ("members", "0040_member_role_assignment_immutability"),
    ]

    operations = [
        migrations.AddField(
            model_name="rolemetadata",
            name="admin_access",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Allow members with this role to enter and see the "
                    "administrative site. This does not grant model or "
                    "application permissions."
                ),
            ),
        ),
        migrations.RunPython(
            enable_admin_access_for_existing_canonical_roles,
            migrations.RunPython.noop,
        ),
    ]
