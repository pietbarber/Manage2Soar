"""Introduce a source-aware legacy role without deleting ambiguous direct grants.

Migration 0045 did not record the source of its direct stats-export grant.
Administrator exceptions use the same user_permissions row, so no migration
can safely decide which rows to revoke. Preserve them for operator review.
"""

from django.db import migrations


STATS_GROUP_NAME = "Stats Mongers"
STATS_SOURCE_KEY = "stats_monger"


def migrate_stats_monger_grants(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    Member = apps.get_model("members", "Member")
    MemberRoleAssignment = apps.get_model("members", "MemberRoleAssignment")
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")

    content_type, _ = ContentType.objects.using(db_alias).get_or_create(
        app_label="logsheet", model="logsheet"
    )
    permission, _ = Permission.objects.using(db_alias).get_or_create(
        content_type=content_type,
        codename="can_export_stats_dump",
        defaults={"name": "Can export raw flight statistics"},
    )
    group, _ = Group.objects.using(db_alias).get_or_create(name=STATS_GROUP_NAME)
    group.permissions.db_manager(db_alias).add(permission)

    # The flag owns only this source-aware Group assignment.  Do not remove
    # other assignments to this Group: a manual/status assignment is
    # independently identifiable and must survive a later flag clear.
    for member in Member.objects.using(db_alias).filter(stats_monger=True).iterator():
        MemberRoleAssignment.objects.using(db_alias).get_or_create(
            member_id=member.pk,
            group_id=group.pk,
            source="legacy",
            source_key=STATS_SOURCE_KEY,
        )
        member.groups.db_manager(db_alias).add(group)

    # 0045 left no provenance on direct rows, so keep every direct grant.
    # Only an operator-reviewed, explicit reconciliation can remove them.


class Migration(migrations.Migration):
    dependencies = [("members", "0052_sync_registered_role_capabilities")]

    operations = [
        migrations.RunPython(
            migrate_stats_monger_grants,
            migrations.RunPython.noop,
        )
    ]
