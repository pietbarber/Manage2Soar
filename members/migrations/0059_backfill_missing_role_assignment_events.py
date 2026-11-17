from django.db import migrations


def backfill_missing_grant_events(apps, schema_editor):
    Assignment = apps.get_model("members", "MemberRoleAssignment")
    Event = apps.get_model("members", "MemberRoleAssignmentEvent")
    Member = apps.get_model("members", "Member")
    Group = apps.get_model("auth", "Group")
    RoleMetadata = apps.get_model("members", "RoleMetadata")
    database = schema_editor.connection.alias
    existing = set(
        Event.objects.using(database)
        .filter(action="grant")
        .values_list("member_id_snapshot", "group_id_snapshot", "source", "source_key")
    )
    members = dict(Member.objects.using(database).values_list("pk", "username"))
    groups = dict(Group.objects.using(database).values_list("pk", "name"))
    role_keys = dict(RoleMetadata.objects.using(database).values_list("group_id", "key"))
    events = []

    def flush_events():
        timestamps = [event.timestamp for event in events]
        Event.objects.using(database).bulk_create(events)
        for event, timestamp in zip(events, timestamps):
            event.timestamp = timestamp
        Event.objects.using(database).bulk_update(events, ["timestamp"])

    for assignment in Assignment.objects.using(database).iterator():
        key = (assignment.member_id, assignment.group_id, assignment.source, assignment.source_key)
        if key in existing:
            continue
        actor_id = assignment.actor_id
        events.append(
            Event(
                member_id=assignment.member_id,
                member_id_snapshot=assignment.member_id,
                member_username=members.get(assignment.member_id, ""),
                group_id=assignment.group_id,
                group_id_snapshot=assignment.group_id,
                group_name=groups.get(assignment.group_id, ""),
                role_key=role_keys.get(assignment.group_id, ""),
                action="grant",
                actor_id=actor_id,
                actor_id_snapshot=actor_id,
                actor_username=members.get(actor_id, ""),
                source=assignment.source,
                source_key=assignment.source_key,
                timestamp=assignment.created_at,
            )
        )
        if len(events) >= 500:
            flush_events()
            events = []
    if events:
        flush_events()


class Migration(migrations.Migration):
    dependencies = [("members", "0058_alter_memberroleassignment_source_key_and_more")]
    operations = [
        migrations.RunPython(backfill_missing_grant_events, migrations.RunPython.noop)
    ]
