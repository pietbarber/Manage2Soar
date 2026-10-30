from django.db import migrations


def grant_safety_report_access(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    Member = apps.get_model("members", "Member")
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    RoleMetadata = apps.get_model("members", "RoleMetadata")
    MemberRoleAssignment = apps.get_model("members", "MemberRoleAssignment")

    content_type, _ = (
        apps.get_model("contenttypes", "ContentType")
        .objects.using(db_alias)
        .get_or_create(
            app_label="members",
            model="safetyreport",
        )
    )
    permission, _ = Permission.objects.using(db_alias).get_or_create(
        content_type=content_type,
        codename="access_safety_reports",
        defaults={"name": "Can access safety reports"},
    )
    group, _ = Group.objects.using(db_alias).get_or_create(name="Safety Officers")
    RoleMetadata.objects.using(db_alias).get_or_create(
        group_id=group.pk,
        defaults={
            "key": "safety_officers",
            "display_name": "Safety Officers",
            "description": "Access to safety reports and safety workflows.",
            "is_builtin": True,
            "is_protected": True,
            "is_system_managed": True,
            "is_assignable": True,
            "sort_order": 30,
        },
    )
    group.permissions.db_manager(db_alias).add(permission)
    for member in Member.objects.using(db_alias).filter(safety_officer=True):
        MemberRoleAssignment.objects.using(db_alias).get_or_create(
            member_id=member.pk,
            group_id=group.pk,
            source="legacy",
            source_key="safety_officer",
        )
        member.groups.db_manager(db_alias).add(group)


def revoke_safety_report_access(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")
    content_type, _ = ContentType.objects.using(db_alias).get_or_create(
        app_label="members", model="safetyreport"
    )
    permission = (
        Permission.objects.using(db_alias)
        .filter(content_type=content_type, codename="access_safety_reports")
        .first()
    )
    group = Group.objects.using(db_alias).filter(name="Safety Officers").first()
    if group and permission:
        group.permissions.db_manager(db_alias).remove(permission)
    if permission:
        permission.delete(using=db_alias)


class Migration(migrations.Migration):
    dependencies = [("members", "0045_map_stats_monger_to_export_permission")]

    operations = [
        migrations.AlterModelOptions(
            name="safetyreport",
            options={
                "ordering": ["-created_at"],
                "permissions": [("access_safety_reports", "Can access safety reports")],
                "verbose_name": "Safety Report",
                "verbose_name_plural": "Safety Reports",
            },
        ),
        migrations.RunPython(grant_safety_report_access, revoke_safety_report_access),
    ]
