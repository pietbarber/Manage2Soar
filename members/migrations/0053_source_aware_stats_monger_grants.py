"""Reconcile the legacy stats-monger export grant with explicit ownership.

Migration 0045 wrote directly to ``user_permissions`` and did not record a
source.  That means a direct grant left by 0045 is indistinguishable from a
direct grant that an administrator added independently.  At this boundary we
therefore use the conservative ownership policy required for this sensitive
permission: every direct stats-export row still present is treated as the
legacy 0045 grant and removed.  Independent access that has recoverable
provenance (a separately assigned Group/role) is not changed and remains
effective through that Group.

Members whose flag is still set receive the source-aware legacy role.  Members
whose flag was cleared before this migration receive no replacement grant, so
the old direct grant cannot survive as export access.
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

    # 0045 left no provenance on direct permission rows.  A direct row still
    # present now is therefore owned by the legacy migration for reconciliation
    # purposes.  Remove it for both currently flagged and already-cleared
    # members; the former now have the source-aware Group assignment above, and
    # the latter must not retain export access.  Independently assigned Groups
    # and their provenance rows are deliberately not touched.
    for member in Member.objects.using(db_alias).filter(
        user_permissions=permission
    ).iterator():
        member.user_permissions.db_manager(db_alias).remove(permission)


class Migration(migrations.Migration):
    dependencies = [("members", "0052_sync_registered_role_capabilities")]

    operations = [
        migrations.RunPython(
            migrate_stats_monger_grants,
            migrations.RunPython.noop,
        )
    ]
