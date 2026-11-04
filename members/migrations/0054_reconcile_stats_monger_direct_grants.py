"""Revoke unowned direct stats-export grants left by migration 0053.

The direct ``user_permissions`` row created by migration 0045 has no source,
creation timestamp, or audit record.  Once migration 0053 has introduced the
source-aware ``legacy:stats_monger`` role, a direct row on a member whose flag
is already clear is therefore treated as the legacy row, not as an
independently owned grant.  This is the only safe ownership decision for a
sensitive export permission: it closes the access gap without guessing about
unrecoverable provenance.

Role/group access is independently represented by ``MemberRoleAssignment``
and is intentionally left untouched.  Such access remains effective when a
member's legacy stats-monger flag is cleared.
"""

from django.db import migrations


def reconcile_cleared_stats_monger_grants(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    Member = apps.get_model("members", "Member")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")

    content_type = (
        ContentType.objects.using(db_alias)
        .filter(app_label="logsheet", model="logsheet")
        .first()
    )
    if content_type is None:
        return
    permission = (
        Permission.objects.using(db_alias)
        .filter(
            content_type=content_type,
            codename="can_export_stats_dump",
        )
        .first()
    )
    if permission is None:
        return

    # Direct permission rows carry no provenance.  A cleared flag is the
    # recoverable evidence that the old direct row is stale.  Do not touch
    # groups or their provenance rows: independently assigned role access is
    # preserved even when it grants this same permission.
    for member in Member.objects.using(db_alias).filter(
        stats_monger=False,
        user_permissions=permission,
    ).iterator():
        member.user_permissions.db_manager(db_alias).remove(permission)


class Migration(migrations.Migration):
    dependencies = [("members", "0053_source_aware_stats_monger_grants")]

    operations = [
        migrations.RunPython(
            reconcile_cleared_stats_monger_grants,
            migrations.RunPython.noop,
        )
    ]
