from django.db import migrations

DIRECTOR_GROUP = "Directors"
DIRECTOR_ROLE_KEY = "directors"
VIEW_PERMISSION = "view_membership_applications"


def grant_director_application_view(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    Member = apps.get_model("members", "Member")
    RoleMetadata = apps.get_model("members", "RoleMetadata")
    ContentType = apps.get_model("contenttypes", "ContentType")

    group, _ = Group.objects.using(db_alias).get_or_create(name=DIRECTOR_GROUP)
    RoleMetadata.objects.using(db_alias).get_or_create(
        group_id=group.pk,
        defaults={
            "key": DIRECTOR_ROLE_KEY,
            "display_name": DIRECTOR_GROUP,
            "description": "Read-only access to membership applications and waitlist.",
            "is_builtin": True,
            "is_protected": True,
            "is_system_managed": True,
            "is_assignable": True,
            "sort_order": 25,
        },
    )

    content_type, _ = ContentType.objects.using(db_alias).get_or_create(
        app_label="members", model="membershipapplication"
    )
    permission, _ = Permission.objects.using(db_alias).get_or_create(
        content_type=content_type,
        codename=VIEW_PERMISSION,
        defaults={"name": "Can view membership applications"},
    )
    group.permissions.db_manager(db_alias).add(permission)

    # Preserve the existing boolean role while giving current Directors the
    # explicit role representation.  The provenance row lets normal role sync
    # retain this grant during the compatibility rollout.
    assignment_model = apps.get_model("members", "MemberRoleAssignment")
    for member in Member.objects.using(db_alias).filter(director=True):
        assignment_model.objects.using(db_alias).get_or_create(
            member_id=member.pk,
            group_id=group.pk,
            source="legacy",
            source_key="director",
        )
        member.groups.db_manager(db_alias).add(group.pk)


def revoke_director_application_view(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")
    group = Group.objects.using(db_alias).filter(name=DIRECTOR_GROUP).first()
    content_type, _ = ContentType.objects.using(db_alias).get_or_create(
        app_label="members", model="membershipapplication"
    )
    permission = (
        Permission.objects.using(db_alias)
        .filter(content_type=content_type, codename=VIEW_PERMISSION)
        .first()
    )
    if group and permission:
        group.permissions.db_manager(db_alias).remove(permission)


class Migration(migrations.Migration):
    dependencies = [("members", "0046_safety_report_access_permission")]

    operations = [
        migrations.AlterModelOptions(
            name="membershipapplication",
            options={
                "ordering": ["-submitted_at"],
                "permissions": [
                    (
                        VIEW_PERMISSION,
                        "Can view membership applications",
                    )
                ],
                "verbose_name": "Membership Application",
                "verbose_name_plural": "Membership Applications",
            },
        ),
        migrations.RunPython(
            grant_director_application_view,
            reverse_code=revoke_director_application_view,
        ),
    ]
